"""
Tests for session notification background tasks.

Tests that the task functions correctly send emails when executed.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.factories import UserFactory
from home.factories import (
    ProjectFactory,
    SessionFactory,
    SessionMembershipFactory,
    SurveyFactory,
    TeamFactory,
    UserSurveyResponseFactory,
)
from home.models import SessionMembership, Waitlist
from home.tasks.session_notifications import (
    send_accepted_email,
    send_acceptance_reminder_email,
    send_rejected_email,
    send_team_welcome_email,
    send_waitlisted_email,
    reject_waitlisted_user,
)


class SendAcceptedEmailTaskTests(TestCase):
    """Tests for the send_accepted_email function."""

    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(title="Test Session")
        cls.user = UserFactory.create(email="accepted@example.com", first_name="Alice")
        cls.membership = SessionMembershipFactory.create(
            session=cls.session,
            user=cls.user,
            role=SessionMembership.DJANGONAUT,
            team=None,
        )

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.session_notifications.email.send")
    def test_sends_acceptance_email(self, mock_send):
        """Test that task sends acceptance email with correct context."""
        send_accepted_email.call(
            membership_id=self.membership.pk,
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["email_template"], "session_accepted")
        self.assertEqual(call_kwargs["recipient_list"], ["accepted@example.com"])
        self.assertIn("acceptance_url", call_kwargs["context"])
        self.assertEqual(call_kwargs["context"]["name"], "Alice")


class SendWaitlistedEmailTaskTests(TestCase):
    """Tests for the send_waitlisted_email function."""

    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(title="Test Session")
        cls.user = UserFactory.create(email="waitlisted@example.com")
        cls.waitlist_entry = Waitlist.objects.create(
            session=cls.session,
            user=cls.user,
        )

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.session_notifications.email.send")
    def test_sends_waitlisted_email(self, mock_send):
        """Test that task sends waitlisted email with correct context."""
        send_waitlisted_email.call(
            waitlist_id=self.waitlist_entry.pk,
            applicant_count=100,
            accepted_count=20,
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["email_template"], "session_waitlisted")
        self.assertEqual(call_kwargs["recipient_list"], ["waitlisted@example.com"])
        self.assertEqual(call_kwargs["context"]["applicant_count"], 100)
        self.assertEqual(call_kwargs["context"]["accepted_count"], 20)


class SendRejectedEmailTaskTests(TestCase):
    """Tests for the send_rejected_email function."""

    @classmethod
    def setUpTestData(cls):
        cls.survey = SurveyFactory.create(name="Application Survey")
        cls.session = SessionFactory.create(
            title="Test Session",
            application_survey=cls.survey,
        )
        cls.user = UserFactory.create(email="rejected@example.com")
        cls.response = UserSurveyResponseFactory.create(
            user=cls.user,
            survey=cls.survey,
        )

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.session_notifications.email.send")
    def test_sends_rejected_email(self, mock_send):
        """Test that task sends rejected email with correct context."""
        send_rejected_email.call(
            user_id=self.user.pk,
            session_id=self.session.pk,
            applicant_count=100,
            accepted_count=20,
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["email_template"], "session_rejected")
        self.assertEqual(call_kwargs["recipient_list"], ["rejected@example.com"])
        self.assertEqual(call_kwargs["context"]["applicant_count"], 100)
        self.assertEqual(call_kwargs["context"]["accepted_count"], 20)


class SendAcceptanceReminderEmailTaskTests(TestCase):
    """Tests for the send_acceptance_reminder_email function."""

    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(title="Test Session")
        cls.user = UserFactory.create(email="pending@example.com", first_name="Bob")
        cls.membership = SessionMembershipFactory.create(
            session=cls.session,
            user=cls.user,
            role=SessionMembership.DJANGONAUT,
            accepted=None,
            team=None,
        )

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.session_notifications.email.send")
    def test_sends_reminder_email(self, mock_send):
        """Test that task sends reminder email with correct context."""
        send_acceptance_reminder_email.call(
            membership_id=self.membership.pk,
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["email_template"], "acceptance_reminder")
        self.assertEqual(call_kwargs["recipient_list"], ["pending@example.com"])
        self.assertIn("acceptance_url", call_kwargs["context"])
        self.assertEqual(call_kwargs["context"]["name"], "Bob")


class SendTeamWelcomeEmailTaskTests(TestCase):
    """Tests for the send_team_welcome_email function."""

    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(title="Test Session")
        cls.project = ProjectFactory.create(name="Django")
        cls.team = TeamFactory.create(
            session=cls.session,
            name="Team Alpha",
            project=cls.project,
        )

        cls.djangonaut = UserFactory.create(email="djangonaut@example.com")
        cls.navigator = UserFactory.create(email="navigator@example.com")

        SessionMembershipFactory.create(
            session=cls.session,
            user=cls.djangonaut,
            team=cls.team,
            role=SessionMembership.DJANGONAUT,
        )
        SessionMembershipFactory.create(
            session=cls.session,
            user=cls.navigator,
            team=cls.team,
            role=SessionMembership.NAVIGATOR,
        )

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
        DISCORD_INVITE_URL="https://discord.gg/test",
    )
    @patch("home.tasks.session_notifications.email.send")
    def test_sends_team_welcome_email(self, mock_send):
        """Test that task sends team welcome email to all members."""
        send_team_welcome_email.call(
            team_id=self.team.pk,
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["email_template"], "team_welcome")
        # All team members should be recipients
        self.assertIn("djangonaut@example.com", call_kwargs["recipient_list"])
        self.assertIn("navigator@example.com", call_kwargs["recipient_list"])
        # Context should include team info
        self.assertEqual(call_kwargs["context"]["team"], self.team)
        self.assertEqual(
            call_kwargs["context"]["discord_invite_url"], "https://discord.gg/test"
        )

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.session_notifications.email.send")
    def test_does_not_send_email_for_empty_team(self, mock_send):
        """Test that task does not send email if team has no members."""
        empty_team = TeamFactory.create(
            session=self.session,
            name="Empty Team",
            project=self.project,
        )

        send_team_welcome_email.call(
            team_id=empty_team.pk,
        )

        mock_send.assert_not_called()


class RejectWaitlistedUserTaskTests(TestCase):
    """Tests for the reject_waitlisted_user function."""

    def setUp(self):
        """Set up test data."""
        self.user = UserFactory.create(
            email="waitlisted@example.com", first_name="Waitlisted"
        )
        self.session = SessionFactory.create(title="Test Session")
        self.waitlist_entry = Waitlist.objects.create(
            user=self.user, session=self.session
        )

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.session_notifications.email.send")
    def test_sends_rejection_email_and_marks_as_notified(self, mock_send):
        """Test that task sends rejection email and marks user as notified."""
        reject_waitlisted_user.call(waitlist_id=self.waitlist_entry.pk)

        # Verify email was sent
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["email_template"], "waitlist_rejection")
        self.assertEqual(call_kwargs["recipient_list"], ["waitlisted@example.com"])

        self.waitlist_entry.refresh_from_db()
        self.assertIsNotNone(self.waitlist_entry.notified_at)

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.session_notifications.email.send")
    def test_does_not_send_duplicate_rejection_email(self, mock_send):
        """Test that task does not send email if user already notified."""
        self.waitlist_entry.notified_at = timezone.now()
        self.waitlist_entry.save()

        reject_waitlisted_user.call(waitlist_id=self.waitlist_entry.pk)
        mock_send.assert_not_called()
