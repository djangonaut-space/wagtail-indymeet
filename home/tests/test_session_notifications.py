"""
Tests for session notification functionality.

Tests the notification system for:
- Sending session result emails (accepted/waitlist/rejected)
- Sending acceptance reminder emails
- Sending team welcome emails
- User acceptance/decline of memberships
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
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

User = get_user_model()


class SessionResultsNotificationTests(TestCase):
    """Tests for sending session result notifications"""

    @classmethod
    def setUpTestData(cls):
        cls.survey = SurveyFactory.create(name="Application Survey")
        cls.session = SessionFactory.create(
            title="Test Session",
            application_survey=cls.survey,
        )

        cls.navigator = UserFactory.create(email="navigator@example.com")
        cls.captain = UserFactory.create(email="captain@example.com")
        # Create accepted users with memberships
        cls.accepted_user1 = UserFactory.create(email="accepted1@example.com")
        cls.accepted_user2 = UserFactory.create(email="accepted2@example.com")

        # Create waitlisted users
        cls.waitlisted_user1 = UserFactory.create(email="waitlisted1@example.com")
        cls.waitlisted_user2 = UserFactory.create(email="waitlisted2@example.com")

        # Create rejected users (applied but not accepted or waitlisted)
        cls.rejected_user1 = UserFactory.create(email="rejected1@example.com")
        cls.rejected_user2 = UserFactory.create(email="rejected2@example.com")

        # Create survey responses for all applicants
        UserSurveyResponseFactory.create(user=cls.accepted_user1, survey=cls.survey)
        UserSurveyResponseFactory.create(user=cls.accepted_user2, survey=cls.survey)
        UserSurveyResponseFactory.create(user=cls.waitlisted_user1, survey=cls.survey)
        UserSurveyResponseFactory.create(user=cls.waitlisted_user2, survey=cls.survey)
        UserSurveyResponseFactory.create(user=cls.rejected_user1, survey=cls.survey)
        UserSurveyResponseFactory.create(user=cls.rejected_user2, survey=cls.survey)

        # Create memberships for accepted users
        cls.membership1 = SessionMembershipFactory.create(
            session=cls.session,
            user=cls.accepted_user1,
            role=SessionMembership.DJANGONAUT,
            team=None,
        )
        cls.membership2 = SessionMembershipFactory.create(
            session=cls.session,
            user=cls.accepted_user2,
            role=SessionMembership.DJANGONAUT,
            team=None,
        )
        SessionMembershipFactory.create(
            session=cls.session,
            user=cls.navigator,
            role=SessionMembership.NAVIGATOR,
            team=None,
        )
        SessionMembershipFactory.create(
            session=cls.session,
            user=cls.captain,
            role=SessionMembership.CAPTAIN,
            team=None,
        )

        # Create waitlist entries
        Waitlist.objects.create(session=cls.session, user=cls.waitlisted_user1)
        Waitlist.objects.create(session=cls.session, user=cls.waitlisted_user2)

        # Create admin user
        cls.admin_user = UserFactory.create(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    def test_send_session_results_view_get(self):
        """Test GET request shows confirmation page with counts"""
        url = reverse("admin:session_send_results", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Session")
        # Check that counts are displayed (only Djangonauts get acceptance emails)
        self.assertContains(response, "1")  # accepted count (only Djangonauts)
        self.assertContains(response, "2")  # waitlisted count
        self.assertContains(response, "2")  # rejected count

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.views.session_notifications.tasks.send_rejected_email")
    @patch("home.views.session_notifications.tasks.send_waitlisted_email")
    @patch("home.views.session_notifications.tasks.send_accepted_email")
    def test_send_session_results_enqueuess(
        self, mock_accepted, mock_waitlisted, mock_rejected
    ):
        """Test POST request enqueues email tasks for all applicants"""
        url = reverse("admin:session_send_results", args=[self.session.id])
        response = self.client.post(
            url,
            {"confirm": "yes", "deadline_days": "7"},
        )

        # Should redirect to session changelist
        self.assertRedirects(response, reverse("admin:home_session_changelist"))

        # Should enqueue 2 accepted tasks (only Djangonauts)
        self.assertEqual(mock_accepted.enqueue.call_count, 2)

        # Should enqueue 2 waitlisted tasks
        self.assertEqual(mock_waitlisted.enqueue.call_count, 2)

        # Should enqueue 2 rejected tasks
        self.assertEqual(mock_rejected.enqueue.call_count, 2)

        # Check that session was marked as sent
        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.results_notifications_sent_at)

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.views.session_notifications.tasks.send_rejected_email")
    @patch("home.views.session_notifications.tasks.send_waitlisted_email")
    @patch("home.views.session_notifications.tasks.send_accepted_email")
    def test_send_session_results_sets_acceptance_deadline(
        self, mock_accepted, mock_waitlisted, mock_rejected
    ):
        """Test that acceptance deadlines are set for Djangonaut memberships only"""
        url = reverse("admin:session_send_results", args=[self.session.id])
        self.client.post(
            url,
            {"confirm": "yes", "deadline_days": "10"},
        )

        # Refresh memberships
        self.membership1.refresh_from_db()
        self.membership2.refresh_from_db()

        # Check deadline is set for Djangonaut only
        expected_deadline = timezone.now().date() + timedelta(days=10)
        set_deadline = SessionMembership.objects.filter(
            acceptance_deadline__isnull=False
        ).values_list("id", flat=True)
        self.assertEqual(set(set_deadline), {self.membership1.id, self.membership2.id})


class AcceptanceReminderTests(TestCase):
    """Tests for sending acceptance reminder emails"""

    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(title="Test Session")

        # Create users who need reminders (not yet accepted)
        cls.pending_user1 = UserFactory.create(email="pending1@example.com")
        cls.pending_user2 = UserFactory.create(email="pending2@example.com")

        # Create user who already accepted
        cls.accepted_user = UserFactory.create(email="accepted@example.com")

        # Create user who declined
        cls.declined_user = UserFactory.create(email="declined@example.com")

        # Create memberships
        cls.pending_membership1 = SessionMembershipFactory.create(
            session=cls.session,
            user=cls.pending_user1,
            accepted=None,
            acceptance_deadline=timezone.now().date() + timedelta(days=5),
            team=None,
        )
        cls.pending_membership2 = SessionMembershipFactory.create(
            session=cls.session,
            user=cls.pending_user2,
            accepted=None,
            acceptance_deadline=timezone.now().date() + timedelta(days=5),
            team=None,
        )
        cls.accepted_membership = SessionMembershipFactory.create(
            session=cls.session,
            user=cls.accepted_user,
            accepted=True,
            accepted_at=timezone.now(),
            acceptance_deadline=timezone.now().date() + timedelta(days=5),
            team=None,
        )
        cls.declined_membership = SessionMembershipFactory.create(
            session=cls.session,
            user=cls.declined_user,
            accepted=False,
            accepted_at=timezone.now(),
            acceptance_deadline=timezone.now().date() + timedelta(days=5),
            team=None,
        )

        # Create admin user
        cls.admin_user = UserFactory.create(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    def test_send_acceptance_reminders_view_get(self):
        """Test GET request shows pending memberships"""
        url = reverse("admin:session_send_acceptance_reminders", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Session")
        self.assertContains(response, "2")  # pending count

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.views.session_notifications.tasks.send_acceptance_reminder_email")
    def test_send_acceptance_reminders_enqueuess(self, mock_reminder):
        """Test POST request enqueues reminder tasks only for pending users"""
        url = reverse("admin:session_send_acceptance_reminders", args=[self.session.id])
        response = self.client.post(url, {"confirm": "yes"})

        # Should redirect
        self.assertRedirects(response, reverse("admin:home_session_changelist"))

        # Should enqueue 2 reminder tasks (only for pending users)
        self.assertEqual(mock_reminder.enqueue.call_count, 2)

        # Verify the correct membership IDs were passed
        enqueued_membership_ids = {
            call.kwargs["membership_id"]
            for call in mock_reminder.enqueue.call_args_list
        }
        self.assertEqual(
            enqueued_membership_ids,
            {self.pending_membership1.id, self.pending_membership2.id},
        )


class TeamWelcomeEmailTests(TestCase):
    """Tests for sending team welcome emails"""

    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(title="Test Session")
        cls.project = ProjectFactory.create(name="Django")

        # Create teams
        cls.team1 = TeamFactory.create(
            session=cls.session,
            name="Team Alpha",
            project=cls.project,
        )
        cls.team2 = TeamFactory.create(
            session=cls.session,
            name="Team Beta",
            project=cls.project,
        )

        # Create team members
        cls.member1 = UserFactory.create(
            email="member1@example.com",
            first_name="Alice",
        )
        cls.member2 = UserFactory.create(
            email="member2@example.com",
            first_name="Bob",
        )
        cls.member3 = UserFactory.create(
            email="member3@example.com",
            first_name="Charlie",
        )

        # Assign members to teams
        SessionMembershipFactory.create(
            session=cls.session,
            user=cls.member1,
            team=cls.team1,
            role=SessionMembership.DJANGONAUT,
        )
        SessionMembershipFactory.create(
            session=cls.session,
            user=cls.member2,
            team=cls.team1,
            role=SessionMembership.NAVIGATOR,
        )
        SessionMembershipFactory.create(
            session=cls.session,
            user=cls.member3,
            team=cls.team2,
            role=SessionMembership.DJANGONAUT,
        )

        # Create admin user
        cls.admin_user = UserFactory.create(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    def test_send_team_welcome_emails_view_get(self):
        """Test GET request shows team counts"""
        url = reverse("admin:session_send_team_welcome_emails", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Session")
        self.assertContains(response, "2")  # team count
        self.assertContains(response, "3")  # member count

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.views.session_notifications.tasks.send_team_welcome_email")
    def test_send_team_welcome_emails_enqueuess(self, mock_team_welcome):
        """Test POST request enqueues team welcome email tasks"""
        url = reverse("admin:session_send_team_welcome_emails", args=[self.session.id])
        response = self.client.post(url, {"confirm": "yes"})

        # Should redirect
        self.assertRedirects(response, reverse("admin:home_session_changelist"))

        # Should enqueue 2 tasks (one per team)
        self.assertEqual(mock_team_welcome.enqueue.call_count, 2)

        # Verify the correct team IDs were passed
        enqueued_team_ids = {
            call.kwargs["team_id"] for call in mock_team_welcome.enqueue.call_args_list
        }
        self.assertEqual(enqueued_team_ids, {self.team1.id, self.team2.id})


class MembershipAcceptanceViewTests(TestCase):
    """Tests for user acceptance/decline of memberships"""

    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(
            title="Test Session",
            start_date=timezone.now().date() + timedelta(days=30),
            end_date=timezone.now().date() + timedelta(days=90),
        )
        cls.user = UserFactory.create(email="user@example.com")
        cls.other_user = UserFactory.create(email="other@example.com")

        cls.membership = SessionMembershipFactory.create(
            session=cls.session,
            user=cls.user,
            accepted=None,
            acceptance_deadline=timezone.now().date() + timedelta(days=7),
            team=None,
        )

    def test_acceptance_view_requires_login(self):
        """Test that acceptance view requires authentication"""
        url = reverse("accept_membership", kwargs={"slug": self.session.slug})
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_acceptance_view_shows_membership_details(self):
        """Test GET request shows membership details"""
        self.client.force_login(self.user)
        url = reverse("accept_membership", kwargs={"slug": self.session.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Session")
        self.assertContains(response, self.membership.get_role_display())

    def test_acceptance_view_prevents_wrong_user(self):
        """Test that users cannot access other users' acceptance pages"""
        self.client.force_login(self.other_user)
        url = reverse("accept_membership", kwargs={"slug": self.session.slug})
        response = self.client.get(url)

        # Should return 404 since other_user has no membership for this session
        self.assertEqual(response.status_code, 404)

    def test_user_can_accept_membership(self):
        """Test POST request to accept membership"""
        self.client.force_login(self.user)
        url = reverse("accept_membership", kwargs={"slug": self.session.slug})
        response = self.client.post(url, {"action": "accept"})

        # Should redirect to session detail
        self.assertRedirects(
            response,
            reverse("session_detail", kwargs={"slug": self.session.slug}),
        )

        # Check membership was updated
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.accepted)
        self.assertIsNotNone(self.membership.accepted_at)

    def test_user_can_decline_membership(self):
        """Test POST request to decline membership"""
        self.client.force_login(self.user)
        url = reverse("accept_membership", kwargs={"slug": self.session.slug})
        response = self.client.post(url, {"action": "decline"})

        # Should redirect to session list
        self.assertRedirects(response, reverse("session_list"))

        # Check membership was updated
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.accepted)
        self.assertIsNotNone(self.membership.accepted_at)

    @override_settings(
        ENVIRONMENT="test",
        ALLOWED_EMAILS_FOR_TESTING=[
            "contact@djangonaut.space",
            "session@djangonaut.space",
        ],
    )
    def test_decline_sends_notification_email(self):
        """Test that declining membership sends notification to organizers"""
        self.client.force_login(self.user)
        url = reverse("accept_membership", kwargs={"slug": self.session.slug})

        # Clear outbox before test
        mail.outbox = []

        response = self.client.post(url, {"action": "decline"})

        # Should send one email to organizers
        self.assertEqual(len(mail.outbox), 1)

        # Check email recipients
        email_recipients = mail.outbox[0].recipients()
        self.assertIn("contact@djangonaut.space", email_recipients)
        self.assertIn("session@djangonaut.space", email_recipients)

        # Check email content
        self.assertIn("declined", mail.outbox[0].subject.lower())
        self.assertIn(self.user.email, mail.outbox[0].body)
        self.assertIn(self.session.title, mail.outbox[0].body)

    def test_cannot_respond_twice(self):
        """Test that users cannot change their response after accepting/declining"""
        # First, accept the membership
        self.membership.accepted = True
        self.membership.accepted_at = timezone.now()
        self.membership.save()

        self.client.force_login(self.user)
        url = reverse("accept_membership", kwargs={"slug": self.session.slug})
        response = self.client.get(url)

        # Should show already responded message
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Membership Confirmed")
        self.assertContains(response, "You confirmed your participation")

    def test_cannot_accept_after_deadline(self):
        """Test that users cannot accept/decline after deadline has passed"""
        # Set deadline to yesterday
        self.membership.acceptance_deadline = timezone.now().date() - timedelta(days=1)
        self.membership.save()

        self.client.force_login(self.user)
        url = reverse("accept_membership", kwargs={"slug": self.session.slug})
        response = self.client.post(url, {"action": "accept"})

        # Should show error and not redirect
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "deadline")
        self.assertContains(response, "has passed")

        # Check membership was not updated
        self.membership.refresh_from_db()
        self.assertIsNone(self.membership.accepted)


class SessionModelNotificationFieldsTests(TestCase):
    """Tests for Session model notification tracking fields"""

    def test_session_has_results_notifications_sent_at_field(self):
        """Test that Session model has results_notifications_sent_at field"""
        session = SessionFactory.create()
        self.assertIsNone(session.results_notifications_sent_at)

        # Set the field
        now = timezone.now()
        session.results_notifications_sent_at = now
        session.save()

        # Verify it was saved
        session.refresh_from_db()
        self.assertEqual(session.results_notifications_sent_at, now)


class SessionMembershipModelAcceptanceFieldsTests(TestCase):
    """Tests for SessionMembership model acceptance tracking fields"""

    def test_membership_has_acceptance_fields(self):
        """Test that SessionMembership has acceptance tracking fields"""
        membership = SessionMembershipFactory.create(team=None)

        # Check default values
        self.assertIsNone(membership.accepted)
        self.assertIsNone(membership.acceptance_deadline)
        self.assertIsNone(membership.accepted_at)

        # Set values
        deadline = timezone.now().date() + timedelta(days=7)
        accepted_at = timezone.now()

        membership.accepted = True
        membership.acceptance_deadline = deadline
        membership.accepted_at = accepted_at
        membership.save()

        # Verify they were saved
        membership.refresh_from_db()
        self.assertTrue(membership.accepted)
        self.assertEqual(membership.acceptance_deadline, deadline)
        self.assertEqual(membership.accepted_at, accepted_at)

    def test_membership_accepted_can_be_null_true_or_false(self):
        """Test that accepted field supports three states"""
        membership = SessionMembershipFactory.create(team=None)

        # Test None (not yet responded)
        membership.accepted = None
        membership.save()
        membership.refresh_from_db()
        self.assertIsNone(membership.accepted)

        # Test True (accepted)
        membership.accepted = True
        membership.save()
        membership.refresh_from_db()
        self.assertTrue(membership.accepted)

        # Test False (declined)
        membership.accepted = False
        membership.save()
        membership.refresh_from_db()
        self.assertFalse(membership.accepted)
