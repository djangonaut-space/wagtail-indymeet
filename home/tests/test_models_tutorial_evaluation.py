"""Tests for the TutorialEvaluation model itself."""

from django.test import TestCase
from django.utils import timezone

from home.factories import SurveyFactory, UserSurveyResponseFactory
from home.models import TutorialEvaluation


def _evaluation(**kwargs):
    response = UserSurveyResponseFactory(survey=SurveyFactory(session=None))
    return TutorialEvaluation.objects.create(user_survey_response=response, **kwargs)


class TutorialEvaluationTests(TestCase):
    def test_is_passing(self):
        """is_passing is true only for a CORRECT result."""
        response = UserSurveyResponseFactory(survey=SurveyFactory(session=None))
        evaluation = TutorialEvaluation.objects.create(
            user_survey_response=response, result=1
        )

        self.assertTrue(evaluation.is_passing)

    def test_is_passing_false(self):
        """Neither an unevaluated (null) result nor a failing one counts as passing."""
        response = UserSurveyResponseFactory(survey=SurveyFactory(session=None))
        evaluation = TutorialEvaluation.objects.create(user_survey_response=response)

        self.assertFalse(evaluation.is_passing)

        evaluation.result = -1
        self.assertFalse(evaluation.is_passing)


class TutorialEvaluationQuerySetTests(TestCase):
    def test_due(self):
        """due() only includes evaluations marked pending."""
        pending = _evaluation(pending=True)
        _evaluation(pending=False)

        self.assertEqual(list(TutorialEvaluation.objects.due()), [pending])

    def test_needing_reminder(self):
        """needing_reminder() only includes evaluated, non-passing, unreminded evaluations."""
        needs_reminder = _evaluation(result=-1, evaluated_at=timezone.now())
        _evaluation(result=1, evaluated_at=timezone.now())  # passing
        _evaluation(result=-1, evaluated_at=None)  # not yet evaluated
        _evaluation(
            result=-1, evaluated_at=timezone.now(), reminder_sent_at=timezone.now()
        )  # already reminded

        self.assertEqual(
            list(TutorialEvaluation.objects.needing_reminder()), [needs_reminder]
        )
