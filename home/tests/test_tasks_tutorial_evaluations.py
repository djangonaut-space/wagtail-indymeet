"""Tests for the tutorial evaluation scheduling and reminder tasks."""

import datetime
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from freezegun import freeze_time

from accounts.factories import UserFactory
from home.factories import (
    QuestionFactory,
    SessionFactory,
    SurveyFactory,
    UserQuestionResponseFactory,
    UserSurveyResponseFactory,
)
from home.integrations.github import Reason, SubmissionResult
from home.models import TutorialEvaluation
from home.tasks.tutorial_evaluations import (
    enqueue_due_tutorial_evaluations,
    evaluate_tutorial_submission_now,
    reevaluate_tutorial_submission,
    schedule_evaluation_if_needed,
    send_due_tutorial_reminders,
    send_tutorial_reminder_now,
)

EMAIL_SETTINGS = dict(
    ENVIRONMENT="production",
    BASE_URL="https://djangonaut.space",
)


def _active_session(**kwargs):
    """A session whose application window is wide open."""
    today = timezone.now().date()
    kwargs.setdefault("application_start_date", today - datetime.timedelta(days=10))
    kwargs.setdefault("application_end_date", today + datetime.timedelta(days=10))
    return SessionFactory(**kwargs)


def _response_for(session):
    survey = SurveyFactory(session=session)
    return UserSurveyResponseFactory(survey=survey)


def _link_response(survey_response, link):
    question = QuestionFactory(
        survey=survey_response.survey,
        label="Please complete the Django contributing tutorial and provide a link below.",
    )
    UserQuestionResponseFactory(
        user_survey_response=survey_response, question=question, value=link
    )


class ScheduleEvaluationIfNeededTests(TestCase):
    def test_no_session(self):
        """A survey response with no session is not scheduled."""
        response = UserSurveyResponseFactory(survey=SurveyFactory(session=None))

        schedule_evaluation_if_needed(response)

        self.assertFalse(TutorialEvaluation.objects.exists())

    @patch("home.tasks.tutorial_evaluations.reevaluate_tutorial_submission")
    def test_schedules_and_enqueues_immediately(self, mock_reevaluate):
        """A response with no prior evaluation is marked pending and enqueued."""
        response = _response_for(_active_session())

        schedule_evaluation_if_needed(response)

        evaluation = TutorialEvaluation.objects.get(user_survey_response=response)
        self.assertTrue(evaluation.pending)
        mock_reevaluate.enqueue.assert_called_once_with(evaluation_id=evaluation.id)

    @patch("home.tasks.tutorial_evaluations.reevaluate_tutorial_submission")
    def test_passing_result(self, mock_reevaluate):
        """An already-passing result is not rescheduled or enqueued."""
        response = _response_for(_active_session())
        TutorialEvaluation.objects.create(user_survey_response=response, result=1)

        schedule_evaluation_if_needed(response)

        evaluation = TutorialEvaluation.objects.get(user_survey_response=response)
        self.assertFalse(evaluation.pending)
        mock_reevaluate.enqueue.assert_not_called()

    @patch("home.tasks.tutorial_evaluations.reevaluate_tutorial_submission")
    def test_failing_result(self, mock_reevaluate):
        """A non-passing result is rescheduled and enqueued for another check."""
        response = _response_for(_active_session())
        TutorialEvaluation.objects.create(user_survey_response=response, result=-1)

        schedule_evaluation_if_needed(response)

        evaluation = TutorialEvaluation.objects.get(user_survey_response=response)
        self.assertTrue(evaluation.pending)
        mock_reevaluate.enqueue.assert_called_once_with(evaluation_id=evaluation.id)

    def test_plain_save(self):
        """Scheduling is orchestrated by the view/service layer, not Model.save()."""
        response = _response_for(_active_session())

        response.score = 5
        response.save()

        self.assertFalse(TutorialEvaluation.objects.exists())


@override_settings(**EMAIL_SETTINGS)
class ReevaluateTutorialSubmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = _active_session(short_name="Session 9")
        cls.user = UserFactory(email="applicant@example.com", first_name="Alex")
        cls.response = _response_for(cls.session)
        cls.response.user = cls.user
        cls.response.save()
        _link_response(cls.response, "https://github.com/alex/django/tree/ticket_1")
        cls.evaluation = TutorialEvaluation.objects.create(
            user_survey_response=cls.response, pending=True
        )

    @patch("home.tasks.tutorial_evaluations.evaluate_submission")
    def test_passing_result(self, mock_evaluate):
        """A passing re-evaluation clears the pending flag."""
        mock_evaluate.return_value = SubmissionResult(
            link="https://github.com/alex/django/tree/ticket_1",
            result=1,
            reasons=(),
            notes="Looks correct.",
        )

        reevaluate_tutorial_submission.call(evaluation_id=self.evaluation.pk)

        self.evaluation.refresh_from_db()
        self.assertEqual(self.evaluation.result, 1)
        self.assertFalse(self.evaluation.pending)
        self.assertIsNone(self.evaluation.reminder_sent_at)
        self.assertEqual(len(mail.outbox), 0)

    @patch("home.tasks.tutorial_evaluations.evaluate_submission")
    def test_failing_result(self, mock_evaluate):
        """A still-failing re-evaluation records the reasons but sends no reminder.

        Reminders are handled independently by ``send_due_tutorial_reminders``.
        """
        mock_evaluate.return_value = SubmissionResult(
            link="https://github.com/alex/django/tree/ticket_1",
            result=-1,
            reasons=(Reason.MISSING_TEST,),
            notes="No test found.",
        )

        reevaluate_tutorial_submission.call(evaluation_id=self.evaluation.pk)

        self.evaluation.refresh_from_db()
        self.assertEqual(self.evaluation.result, -1)
        self.assertEqual(list(self.evaluation.reasons), ["missing_test"])
        self.assertFalse(self.evaluation.pending)
        self.assertIsNone(self.evaluation.reminder_sent_at)
        self.assertEqual(len(mail.outbox), 0)

    @patch("home.tasks.tutorial_evaluations.evaluate_submission")
    def test_evaluates_linked_submission(self, mock_evaluate):
        """The saved tutorial link, not some other value, is what gets evaluated."""
        mock_evaluate.return_value = SubmissionResult(
            link="https://github.com/alex/django/tree/ticket_1",
            result=1,
            reasons=(),
            notes="",
        )

        reevaluate_tutorial_submission.call(evaluation_id=self.evaluation.pk)

        mock_evaluate.assert_called_once_with(
            "https://github.com/alex/django/tree/ticket_1"
        )

    @patch("home.tasks.tutorial_evaluations.evaluate_submission")
    def test_no_link_answered(self, mock_evaluate):
        """An applicant who hasn't answered the tutorial question yet still gets checked."""
        mock_evaluate.return_value = SubmissionResult(
            link="",
            result=0,
            reasons=(Reason.UNPARSEABLE_LINK,),
            notes="No link given.",
        )
        response = _response_for(self.session)
        evaluation = TutorialEvaluation.objects.create(
            user_survey_response=response, pending=True
        )

        reevaluate_tutorial_submission.call(evaluation_id=evaluation.pk)

        mock_evaluate.assert_called_once_with("")

    @patch("home.tasks.tutorial_evaluations.evaluate_submission")
    def test_not_due(self, mock_evaluate):
        """A stale enqueue (already processed) must not re-run."""
        self.evaluation.pending = False
        self.evaluation.save()

        reevaluate_tutorial_submission.call(evaluation_id=self.evaluation.pk)

        mock_evaluate.assert_not_called()

    @patch("home.tasks.tutorial_evaluations.evaluate_submission")
    def test_missing_evaluation(self, mock_evaluate):
        """An evaluation id that no longer exists is a no-op."""
        reevaluate_tutorial_submission.call(evaluation_id=999999)

        mock_evaluate.assert_not_called()


@override_settings(**EMAIL_SETTINGS)
class EvaluateTutorialSubmissionNowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = _active_session(short_name="Session 9")
        cls.user = UserFactory(email="applicant@example.com", first_name="Alex")
        cls.response = _response_for(cls.session)
        cls.response.user = cls.user
        cls.response.save()
        _link_response(cls.response, "https://github.com/alex/django/tree/ticket_1")

    @patch("home.tasks.tutorial_evaluations.evaluate_submission")
    def test_creates_evaluation_when_none_exists(self, mock_evaluate):
        """No prior TutorialEvaluation is needed - one is created on demand."""
        mock_evaluate.return_value = SubmissionResult(
            link="https://github.com/alex/django/tree/ticket_1",
            result=1,
            reasons=(),
            notes="Looks correct.",
        )

        evaluate_tutorial_submission_now.call(user_survey_response_id=self.response.pk)

        evaluation = TutorialEvaluation.objects.get(user_survey_response=self.response)
        self.assertEqual(evaluation.result, 1)
        self.assertIsNotNone(evaluation.evaluated_at)

    @patch("home.tasks.tutorial_evaluations.evaluate_submission")
    def test_ignores_schedule(self, mock_evaluate):
        """Runs immediately even when nothing is due (pending is False).

        Records the result only; the reminder email is left to
        ``send_due_tutorial_reminders``.
        """
        mock_evaluate.return_value = SubmissionResult(
            link="https://github.com/alex/django/tree/ticket_1",
            result=-1,
            reasons=(Reason.MISSING_TEST,),
            notes="No test found.",
        )
        evaluation = TutorialEvaluation.objects.create(
            user_survey_response=self.response, pending=False
        )

        evaluate_tutorial_submission_now.call(user_survey_response_id=self.response.pk)

        evaluation.refresh_from_db()
        self.assertEqual(evaluation.result, -1)
        self.assertIsNone(evaluation.reminder_sent_at)
        self.assertEqual(len(mail.outbox), 0)

    @patch("home.tasks.tutorial_evaluations.evaluate_submission")
    def test_missing_response(self, mock_evaluate):
        """A survey response id that no longer exists is a no-op."""
        evaluate_tutorial_submission_now.call(user_survey_response_id=999999)

        mock_evaluate.assert_not_called()


class EnqueueDueTutorialEvaluationsTests(TestCase):
    @patch("home.tasks.tutorial_evaluations.reevaluate_tutorial_submission")
    def test_enqueues_due_only(self, mock_reevaluate):
        """Only evaluations marked pending get re-checked."""
        session = _active_session()
        due = TutorialEvaluation.objects.create(
            user_survey_response=_response_for(session), pending=True
        )
        TutorialEvaluation.objects.create(
            user_survey_response=_response_for(session), pending=False
        )

        enqueue_due_tutorial_evaluations.call()

        mock_reevaluate.enqueue.assert_called_once_with(evaluation_id=due.id)


@override_settings(**EMAIL_SETTINGS)
class SendDueTutorialRemindersTests(TestCase):
    def test_reminds_unreminded_non_passing_evaluations(self):
        """A non-passing, evaluated, not-yet-reminded evaluation gets a reminder."""
        session = _active_session(short_name="Session 9")
        user = UserFactory(email="applicant@example.com", first_name="Alex")
        response = _response_for(session)
        response.user = user
        response.save()
        evaluation = TutorialEvaluation.objects.create(
            user_survey_response=response,
            result=-1,
            evaluated_at=timezone.now(),
        )

        send_due_tutorial_reminders.call()

        evaluation.refresh_from_db()
        self.assertIsNotNone(evaluation.reminder_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["applicant@example.com"])
        self.assertIn("Session 9", sent.subject)
        self.assertIn("Django contribution tutorial", sent.body)

    def test_skips_already_reminded(self):
        """An evaluation that already got a reminder isn't emailed again."""
        response = _response_for(_active_session())
        TutorialEvaluation.objects.create(
            user_survey_response=response,
            result=-1,
            evaluated_at=timezone.now(),
            reminder_sent_at=timezone.now(),
        )

        send_due_tutorial_reminders.call()

        self.assertEqual(len(mail.outbox), 0)

    def test_skips_passing_result(self):
        """A passing evaluation never needs a reminder."""
        response = _response_for(_active_session())
        TutorialEvaluation.objects.create(
            user_survey_response=response,
            result=1,
            evaluated_at=timezone.now(),
        )

        send_due_tutorial_reminders.call()

        self.assertEqual(len(mail.outbox), 0)

    def test_skips_unevaluated(self):
        """An evaluation that hasn't run yet has nothing to remind about."""
        response = _response_for(_active_session())
        TutorialEvaluation.objects.create(user_survey_response=response)

        send_due_tutorial_reminders.call()

        self.assertEqual(len(mail.outbox), 0)

    def test_deadline_too_close(self):
        """Less than 12 hours left before the deadline: too late for a reminder to help."""
        with freeze_time("2026-01-02 06:00:00"):
            session = _active_session(application_end_date=datetime.date(2026, 1, 1))
            response = _response_for(session)
            TutorialEvaluation.objects.create(
                user_survey_response=response,
                result=-1,
                evaluated_at=timezone.now(),
            )

            send_due_tutorial_reminders.call()

            self.assertEqual(len(mail.outbox), 0)

    def test_deadline_not_too_close(self):
        """More than 12 hours left before the deadline: still worth reminding."""
        with freeze_time("2026-01-01 11:00:00"):
            session = _active_session(application_end_date=datetime.date(2026, 1, 1))
            response = _response_for(session)
            TutorialEvaluation.objects.create(
                user_survey_response=response,
                result=-1,
                evaluated_at=timezone.now(),
            )

            send_due_tutorial_reminders.call()

            self.assertEqual(len(mail.outbox), 1)

    def test_no_session_ignores_deadline(self):
        """A response with no session has no deadline to reason about, so it's reminded."""
        survey = SurveyFactory(session=None)
        response = UserSurveyResponseFactory(survey=survey)
        TutorialEvaluation.objects.create(
            user_survey_response=response,
            result=-1,
            evaluated_at=timezone.now(),
        )

        send_due_tutorial_reminders.call()

        self.assertEqual(len(mail.outbox), 1)


@override_settings(**EMAIL_SETTINGS)
class SendTutorialReminderNowTests(TestCase):
    def test_sends_reminder_and_marks_sent(self):
        """The reminder email goes out immediately and reminder_sent_at is stamped."""
        session = _active_session(short_name="Session 9")
        user = UserFactory(email="applicant@example.com", first_name="Alex")
        response = _response_for(session)
        response.user = user
        response.save()
        evaluation = TutorialEvaluation.objects.create(
            user_survey_response=response,
            result=-1,
            evaluated_at=timezone.now(),
        )

        send_tutorial_reminder_now.call(evaluation_id=evaluation.pk)

        evaluation.refresh_from_db()
        self.assertIsNotNone(evaluation.reminder_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["applicant@example.com"])

    def test_ignores_already_reminded(self):
        """A manual re-send goes out even if a reminder was already sent."""
        response = _response_for(_active_session())
        evaluation = TutorialEvaluation.objects.create(
            user_survey_response=response,
            result=-1,
            evaluated_at=timezone.now(),
            reminder_sent_at=timezone.now(),
        )

        send_tutorial_reminder_now.call(evaluation_id=evaluation.pk)

        self.assertEqual(len(mail.outbox), 1)

    def test_missing_evaluation(self):
        """An evaluation id that no longer exists is a no-op."""
        send_tutorial_reminder_now.call(evaluation_id=999999)

        self.assertEqual(len(mail.outbox), 0)
