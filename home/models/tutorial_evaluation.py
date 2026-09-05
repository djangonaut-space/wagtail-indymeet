"""Scheduling and results for automated make_toast tutorial evaluations.

Applicants link their completed contribution tutorial submission as part of
their session application. Evaluating a link hits the GitHub API (see
``home.integrations.github.evaluate_submission`` and
``home.tasks.tutorial_evaluations``).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from home.models.base import BaseModel


class Result(models.IntegerChoices):
    """The verdict from evaluating a tutorial submission. See ``home.integrations.github``."""

    INCORRECT = -1, _("Incorrect")
    PARTIAL = 0, _("Partial")
    CORRECT = 1, _("Correct")
    UNCERTAIN = 2, _("Uncertain")


class TutorialEvaluationQuerySet(models.QuerySet):
    def due(self) -> "TutorialEvaluationQuerySet":
        """Filter to evaluations the scheduled job should re-check."""
        return self.filter(pending=True)

    def needing_reminder(self) -> "TutorialEvaluationQuerySet":
        """Filter to evaluated, non-passing evaluations that haven't been reminded about yet."""
        return self.filter(
            evaluated_at__isnull=False, reminder_sent_at__isnull=True
        ).exclude(result=Result.CORRECT)


class TutorialEvaluation(BaseModel):
    """The latest make_toast tutorial evaluation for one survey response, and its schedule.

    ``reasons`` holds ``home.integrations.github.Reason`` values (as plain
    strings); empty when the submission is fully correct.
    """

    user_survey_response = models.OneToOneField(
        "home.UserSurveyResponse",
        related_name="tutorial_evaluation",
        on_delete=models.CASCADE,
    )
    link = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="The tutorial link that was last evaluated.",
    )
    result = models.SmallIntegerField(
        choices=Result,
        null=True,
        blank=True,
        help_text="Null means it hasn't been evaluated yet.",
    )
    reasons = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, default="")
    evaluated_at = models.DateTimeField(null=True, blank=True)
    pending = models.BooleanField(
        default=False,
        help_text="Set when a re-check has been scheduled but not yet run.",
    )
    reminder_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the applicant was last emailed about a non-passing result.",
    )

    objects = models.Manager.from_queryset(TutorialEvaluationQuerySet)()

    def __str__(self):
        return f"Tutorial evaluation for survey response {self.user_survey_response_id}"

    @property
    def is_passing(self) -> bool:
        return self.result == Result.CORRECT
