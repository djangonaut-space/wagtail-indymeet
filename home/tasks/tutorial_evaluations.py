import datetime

from crontask import cron
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_tasks import task

from home import email
from home.integrations.github import SubmissionResult, evaluate_submission
from home.models import TutorialEvaluation, UserSurveyResponse
from home.models.tutorial_evaluation import Result

# The key of the application survey question that collects the tutorial
# submission link, derived from its label via Question.save()'s slugify().
# HACK: This is intentional and fragile, sorry
TUTORIAL_QUESTION_KEY = (
    "please-complete-the-django-contributing-tutorial-and-provide-a-link-below"
)

REMINDER_DEADLINE_CUTOFF = datetime.timedelta(hours=12)


def _tutorial_link(user_survey_response: UserSurveyResponse) -> str:
    return (
        user_survey_response.userquestionresponse_set.filter(
            question__key=TUTORIAL_QUESTION_KEY
        )
        .values_list("value", flat=True)
        .first()
        or ""
    )


def schedule_evaluation_if_needed(user_survey_response: UserSurveyResponse) -> None:
    """Queue an immediate GitHub tutorial check, unless it's pointless to do so.

    Whether there's still enough time before the deadline for a reminder to
    help is decided later, by ``send_due_tutorial_reminders``.

    Marked pending immediately and left for ``enqueue_due_tutorial_evaluations``
    to pick up too: if the enqueue below never runs (e.g. a deploy between the
    two), the daily job still catches it.
    """
    if user_survey_response.survey.session_id is None:
        return

    with transaction.atomic():
        evaluation, _ = TutorialEvaluation.objects.select_for_update().get_or_create(
            user_survey_response=user_survey_response
        )
        if evaluation.result == Result.CORRECT:
            return

        evaluation.pending = True
        evaluation.save(update_fields=["pending", "updated_at"])

    reevaluate_tutorial_submission.enqueue(evaluation_id=evaluation.id)


@cron("0 11 * * *")
@task()
def enqueue_due_tutorial_evaluations() -> None:
    """Enqueue a re-check for every tutorial evaluation that has come due.

    A safety net alongside the immediate enqueue in
    ``schedule_evaluation_if_needed``: this catches evaluations whose
    immediate check never ran or errored out.
    """
    evaluation_ids = TutorialEvaluation.objects.due().values_list("id", flat=True)
    for evaluation_id in evaluation_ids:
        reevaluate_tutorial_submission.enqueue(evaluation_id=evaluation_id)


def _record_result(evaluation: TutorialEvaluation, result: SubmissionResult) -> None:
    """Only records the result: whether a reminder email is due is decided
    separately by ``send_due_tutorial_reminders``, so a failure sending mail
    can never roll back a successfully recorded evaluation, and vice versa.
    """
    evaluation.link = result.link
    evaluation.result = result.result
    evaluation.reasons = list(result.reasons)
    evaluation.notes = result.notes
    evaluation.evaluated_at = timezone.now()
    evaluation.pending = False
    evaluation.save()


@task()
def reevaluate_tutorial_submission(evaluation_id: int) -> None:
    """Re-evaluate one due submission and record the outcome.

    The GitHub check runs before any row lock is taken, since it's a slow
    external call; only the write-back is done under ``select_for_update()``,
    which re-confirms the evaluation is still due in case it was cleared by
    a concurrent check in the meantime.
    """
    evaluation = (
        TutorialEvaluation.objects.due()
        .select_related("user_survey_response")
        .filter(pk=evaluation_id)
        .first()
    )
    if evaluation is None:
        return

    result = evaluate_submission(_tutorial_link(evaluation.user_survey_response))

    with transaction.atomic():
        evaluation = (
            TutorialEvaluation.objects.due()
            .select_for_update()
            .filter(pk=evaluation_id)
            .first()
        )
        if evaluation is None:
            return

        _record_result(evaluation, result)


@task()
def evaluate_tutorial_submission_now(user_survey_response_id: int) -> None:
    """Evaluate a submission immediately, regardless of its check schedule.

    Triggered manually (e.g. a "Re-evaluate tutorial submission" admin
    action), rather than by the daily due-evaluation cron job, so this
    doesn't require (or consult) the ``pending`` flag. As in
    ``reevaluate_tutorial_submission``, the GitHub check runs before any row
    lock is taken.
    """
    survey_response = (
        UserSurveyResponse.objects.select_related("user")
        .filter(pk=user_survey_response_id)
        .first()
    )
    if survey_response is None:
        return

    result = evaluate_submission(_tutorial_link(survey_response))

    with transaction.atomic():
        evaluation, _ = TutorialEvaluation.objects.select_for_update().get_or_create(
            user_survey_response=survey_response
        )
        _record_result(evaluation, result)


@cron("0 12 * * *")
@task()
def send_due_tutorial_reminders() -> None:
    """Email applicants whose recorded tutorial result still isn't passing.

    Runs independently of evaluation: it only looks at what's already on file
    (and hasn't been reminded about yet), regardless of how that evaluation
    was triggered - immediately after save, the daily catch-up job, or a
    manual admin re-check. Skipped when the response's session has less than
    ``REMINDER_DEADLINE_CUTOFF`` left before its application deadline, since
    the applicant wouldn't have time left to act on the reminder.
    """
    now = timezone.now()
    evaluation_ids = TutorialEvaluation.objects.needing_reminder().values_list(
        "id", flat=True
    )
    for evaluation_id in evaluation_ids:
        with transaction.atomic():
            evaluation = (
                TutorialEvaluation.objects.needing_reminder()
                .select_for_update()
                # Not survey__session too: Survey.session is nullable, and Postgres
                # can't lock across the nullable side of the resulting outer join.
                .select_related(
                    "user_survey_response__user", "user_survey_response__survey"
                )
                .filter(pk=evaluation_id)
                .first()
            )
            if evaluation is None:
                continue

            session = evaluation.user_survey_response.survey.session
            if (
                session is not None
                and now + REMINDER_DEADLINE_CUTOFF
                >= session.application_end_anywhere_on_earth()
            ):
                continue

            _send_reminder(evaluation.user_survey_response)
            evaluation.reminder_sent_at = timezone.now()
            evaluation.save(update_fields=["reminder_sent_at", "updated_at"])


def _send_reminder(survey_response: UserSurveyResponse) -> None:
    session = survey_response.survey.session
    email.send(
        from_email=settings.SESSIONS_FROM_EMAIL,
        email_template="tutorial_reminder",
        recipient_list=[survey_response.user.email],
        context={
            "user": survey_response.user,
            "name": survey_response.user.first_name or survey_response.user.email,
            "session": session,
            "response": survey_response,
            "cta_link": survey_response.get_full_url(),
        },
    )
