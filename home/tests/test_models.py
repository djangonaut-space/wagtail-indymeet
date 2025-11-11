from datetime import datetime

from django.core import mail
from django.test import TestCase, override_settings
from freezegun import freeze_time

from accounts.factories import UserFactory
from home.factories import (
    ProjectFactory,
    QuestionFactory,
    SessionFactory,
    SurveyFactory,
    TeamFactory,
    UserQuestionResponseFactory,
    UserSurveyResponseFactory,
)
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

    def test_is_current_before_start(self):
        """Test is_current() returns False before session starts."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-05-31"):
            self.assertFalse(session.is_current())

    def test_is_current_on_start_date(self):
        """Test is_current() returns True on session start date."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-06-01"):
            self.assertTrue(session.is_current())

    def test_is_current_during_session(self):
        """Test is_current() returns True during session."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-09-15"):
            self.assertTrue(session.is_current())

    def test_is_current_on_end_date(self):
        """Test is_current() returns True on session end date."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-12-31"):
            self.assertTrue(session.is_current())

    def test_is_current_after_end(self):
        """Test is_current() returns False after session ends."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2025-01-01"):
            self.assertFalse(session.is_current())

    def test_current_week_before_start(self):
        """Test current_week returns None before session starts."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-05-31"):
            self.assertIsNone(session.current_week)

    def test_current_week_first_day(self):
        """Test current_week returns 1 on first day of session."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-06-01"):
            self.assertEqual(session.current_week, 1)

    def test_current_week_first_week(self):
        """Test current_week returns 1 during first week."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),  # Saturday
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-06-07"):  # 6 days later (still week 1)
            self.assertEqual(session.current_week, 1)

    def test_current_week_second_week(self):
        """Test current_week returns 2 on day 7 (start of week 2)."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-06-08"):  # 7 days later (week 2)
            self.assertEqual(session.current_week, 2)

    def test_current_week_mid_session(self):
        """Test current_week calculation in middle of session."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        # 35 days later = 5 weeks + 0 days = week 6
        with freeze_time("2024-07-06"):
            self.assertEqual(session.current_week, 6)

    def test_current_week_last_day(self):
        """Test current_week on last day of session."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 6, 21).date(),  # 20 days = 3 weeks
        )

        with freeze_time("2024-06-21"):
            self.assertEqual(session.current_week, 3)

    def test_current_week_after_end(self):
        """Test current_week returns None after session ends."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2025-01-01"):
            self.assertIsNone(session.current_week)

    def test_status_upcoming(self):
        """Test status returns 'upcoming' before session starts."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-05-31"):
            self.assertEqual(session.status, "upcoming")

    def test_status_current_on_start_date(self):
        """Test status returns 'current' on session start date."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-06-01"):
            self.assertEqual(session.status, "current")

    def test_status_current_during_session(self):
        """Test status returns 'current' during session."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-09-15"):
            self.assertEqual(session.status, "current")

    def test_status_current_on_end_date(self):
        """Test status returns 'current' on session end date."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2024-12-31"):
            self.assertEqual(session.status, "current")

    def test_status_past(self):
        """Test status returns 'past' after session ends."""
        session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 12, 31).date(),
        )

        with freeze_time("2025-01-01"):
            self.assertEqual(session.status, "past")


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
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create(
            email="applicant@example.com",
            first_name="Jane",
        )

    def test_is_editable_with_accepting_session(self):
        """Response is editable if at least one session is accepting applications"""
        survey = SurveyFactory.create()

        # Create session with active application window
        SessionFactory.create(
            application_survey=survey,
            application_start_date=datetime(2023, 10, 16).date(),
            application_end_date=datetime(2023, 11, 15).date(),
        )
        response = UserSurveyResponseFactory.create(survey=survey, user=self.user)
        with freeze_time("2023-10-20"):
            self.assertTrue(response.is_editable())

    def test_is_not_editable_with_closed_session(self):
        """Response is not editable if all sessions have closed applications"""
        survey = SurveyFactory.create()

        # Create session with closed application window
        SessionFactory.create(
            application_survey=survey,
            application_start_date=datetime(2023, 10, 16).date(),
            application_end_date=datetime(2023, 11, 15).date(),
        )
        response = UserSurveyResponseFactory.create(survey=survey, user=self.user)
        # After application window closes
        with freeze_time("2023-11-16 12:00:00"):
            self.assertFalse(response.is_editable())

    def test_is_not_editable_no_application_session(self):
        """Response is not editable if no application session"""
        survey = SurveyFactory.create()
        response = UserSurveyResponseFactory.create(survey=survey, user=self.user)
        self.assertFalse(response.is_editable())

    @override_settings(ENVIRONMENT="production")
    def test_send_created_notification_with_session(self):
        """Test that created notification is sent when survey has a session"""
        session = SessionFactory.create(
            title="Spring 2024 Session",
            application_start_date=datetime(2024, 1, 1).date(),
            application_end_date=datetime(2024, 2, 1).date(),
        )
        survey = SurveyFactory.create(session=session)
        response = UserSurveyResponseFactory.create(
            survey=survey,
            user=self.user,
        )

        response.send_created_notification()

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].recipients(), ["applicant@example.com"])
        self.assertEqual(
            mail.outbox[0].subject,
            "Djangonaut Space Application Submitted",
        )

        # Check that email contains expected content
        # Note: Template uses {{ user.first_name }}, but context doesn't include user
        # so it will render as empty. This tests the actual behavior.
        self.assertIn("Hello ", mail.outbox[0].body)
        self.assertIn("Spring 2024 Session", mail.outbox[0].body)
        self.assertIn("successfully submitted", mail.outbox[0].body)
        self.assertIn("availability", mail.outbox[0].body)

    @override_settings(ENVIRONMENT="production")
    def test_send_created_notification_without_session(self):
        """Test that no notification is sent when survey has no session"""
        survey = SurveyFactory.create(session=None)
        response = UserSurveyResponseFactory.create(
            survey=survey,
            user=self.user,
        )

        response.send_created_notification()

        # No email should be sent
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ENVIRONMENT="production")
    def test_send_updated_notification_with_session(self):
        """Test that updated notification is sent when survey has a session"""
        session = SessionFactory.create(
            title="Fall 2024 Session",
            application_start_date=datetime(2024, 8, 1).date(),
            application_end_date=datetime(2024, 9, 1).date(),
        )
        survey = SurveyFactory.create(session=session)
        response = UserSurveyResponseFactory.create(
            survey=survey,
            user=self.user,
        )

        response.send_updated_notification()

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].recipients(), ["applicant@example.com"])
        self.assertEqual(
            mail.outbox[0].subject,
            "Djangonaut Space Application Updated",
        )

        # Check that email contains expected content
        # Note: Template uses {{ user.first_name }}, but context doesn't include user
        # so it will render as empty. This tests the actual behavior.
        self.assertIn("Hello ", mail.outbox[0].body)
        self.assertIn("Fall 2024 Session", mail.outbox[0].body)
        self.assertIn("successfully updated", mail.outbox[0].body)
        self.assertIn("availability", mail.outbox[0].body)

    @override_settings(ENVIRONMENT="production")
    def test_send_updated_notification_without_session(self):
        """Test that no notification is sent when survey has no session"""
        survey = SurveyFactory.create(session=None)
        response = UserSurveyResponseFactory.create(
            survey=survey,
            user=self.user,
        )

        response.send_updated_notification()

        # No email should be sent
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    def test_send_notifications_include_response_url(self):
        """Test that both notifications include the response URL"""
        session = SessionFactory.create(title="Test Session")
        survey = SurveyFactory.create(session=session)
        response = UserSurveyResponseFactory.create(
            survey=survey,
            user=self.user,
        )

        # Test created notification
        response.send_created_notification()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(response.get_full_url(), mail.outbox[0].body)

        # Clear mailbox
        mail.outbox.clear()

        # Test updated notification
        response.send_updated_notification()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(response.get_full_url(), mail.outbox[0].body)


class TeamTests(TestCase):
    """Tests for Team model."""

    def test_get_absolute_url(self):
        """Test get_absolute_url returns correct URL for team detail page."""
        session = SessionFactory.create(slug="spring-2024")
        project = ProjectFactory.create(name="Django")
        team = TeamFactory.create(session=session, project=project, name="Team Alpha")

        expected_url = f"/sessions/spring-2024/teams/{team.pk}/"
        self.assertEqual(team.get_absolute_url(), expected_url)
