from datetime import datetime

from django.test import TestCase
from freezegun import freeze_time

from accounts.factories import UserFactory
from home.factories import QuestionFactory
from home.factories import SessionFactory
from home.factories import SurveyFactory
from home.factories import UserQuestionResponseFactory
from home.factories import UserSurveyResponseFactory
from home.models import Session
from home.models import TypeField


class SessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(
            application_start_date=datetime(2023, 10, 16).date(),
            application_end_date=datetime(2023, 11, 15).date(),
        )

    def test_is_accepting_applications(self):
        # Ensure that the types of fields are from django, not from when
        # I created the object in memory
        self.session.refresh_from_db()

        with freeze_time("2023-10-15"):
            self.assertFalse(self.session.is_accepting_applications())

        with freeze_time("2023-10-15 12:00:00"):
            # In UTC, so this is the 16th somewhere in the world
            self.assertTrue(self.session.is_accepting_applications())

        with freeze_time("2023-10-16"):
            self.assertTrue(self.session.is_accepting_applications())

        with freeze_time("2023-11-15"):
            self.assertTrue(self.session.is_accepting_applications())

        with freeze_time("2023-11-16"):
            # In UTC, so is the 15th still somewhere in the world
            self.assertTrue(self.session.is_accepting_applications())

        with freeze_time("2023-11-16 12:00:00"):
            # No longer 15th AoE
            self.assertFalse(self.session.is_accepting_applications())


class UserQuestionResponseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.survey = SurveyFactory.create()
        cls.user_survey_response = UserSurveyResponseFactory.create(
            survey=cls.survey, user=cls.user
        )

    def test_get_value_rating(self):
        question = QuestionFactory.create(
            survey=self.survey,
            type_field=TypeField.RATING,
            choices="5",
        )
        response = UserQuestionResponseFactory.create(
            question=question, value="2", user_survey_response=self.user_survey_response
        )
        self.assertEqual(
            response.get_value,
            (
                f'<div class="flex content-center" id="parent_start_{question.id}">'
                '<i class ="rating__star rating_active"> </i>'
                '<i class ="rating__star rating_active"> </i>'
                '<i class ="rating__star rating_inactive"> </i>'
                '<i class ="rating__star rating_inactive"> </i>'
                '<i class ="rating__star rating_inactive"> </i></div>'
            ),
        )

    def test_get_value_url(self):
        question = QuestionFactory.create(
            survey=self.survey,
            type_field=TypeField.URL,
        )
        response = UserQuestionResponseFactory.create(
            question=question,
            value="https://example.com",
            user_survey_response=self.user_survey_response,
        )
        self.assertEqual(
            response.get_value,
            '<a href="https://example.com" target="_blank">https://example.com</a>',
        )


class UserSurveyResponseTests(TestCase):
    def test_is_editable_with_accepting_session(self):
        """Response is editable if at least one session is accepting applications"""
        survey = SurveyFactory.create()
        user = UserFactory.create()

        # Create session with active application window
        SessionFactory.create(
            application_survey=survey,
            application_start_date=datetime(2023, 10, 16).date(),
            application_end_date=datetime(2023, 11, 15).date(),
        )
        response = UserSurveyResponseFactory.create(survey=survey, user=user)
        with freeze_time("2023-10-20"):
            self.assertTrue(response.is_editable())

    def test_is_not_editable_with_closed_session(self):
        """Response is not editable if all sessions have closed applications"""
        survey = SurveyFactory.create()
        user = UserFactory.create()

        # Create session with closed application window
        SessionFactory.create(
            application_survey=survey,
            application_start_date=datetime(2023, 10, 16).date(),
            application_end_date=datetime(2023, 11, 15).date(),
        )
        response = UserSurveyResponseFactory.create(survey=survey, user=user)
        # After application window closes
        with freeze_time("2023-11-16 12:00:00"):
            self.assertFalse(response.is_editable())

    def test_is_not_editable_no_application_sessions(self):
        """Response is not editable if no application sessions"""
        survey = SurveyFactory.create()
        user = UserFactory.create()
        response = UserSurveyResponseFactory.create(survey=survey, user=user)
        self.assertFalse(response.is_editable())
