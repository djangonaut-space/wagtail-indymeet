"""Tests for waitlist management functionality."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts.factories import UserFactory
from home.admin import WaitlistAdmin, SessionMembershipAdmin
from home.factories import SessionFactory, SessionMembershipFactory
from home.models import SessionMembership, Waitlist
from home.views.session_notifications import send_membership_acceptance_emails


class WaitlistAdminActionsTests(TestCase):
    """Tests for WaitlistAdmin admin actions."""

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.admin = WaitlistAdmin(Waitlist, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com",
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_superuser=True,
        )
        self.session = SessionFactory.create(title="Test Session", slug="test-session")

    def _get_request(self):
        """Create a request with session and messages support."""
        request = self.factory.post("/admin/home/waitlist/")
        request.user = self.superuser

        # Add session support
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        # Add messages support
        messages = FallbackStorage(request)
        setattr(request, "_messages", messages)

        return request

    @patch("home.views.session_notifications.email.send")
    def test_reject_waitlisted_users_action(self, mock_send):
        """Test the reject_waitlisted_users_action admin action."""
        # Create waitlisted users
        user1 = UserFactory.create(
            email="user1@example.com", first_name="User", last_name="One"
        )
        user2 = UserFactory.create(
            email="user2@example.com", first_name="User", last_name="Two"
        )
        waitlist1 = Waitlist.objects.create(user=user1, session=self.session)
        waitlist2 = Waitlist.objects.create(user=user2, session=self.session)

        # Execute the action
        request = self._get_request()
        queryset = Waitlist.objects.filter(id__in=[waitlist1.id, waitlist2.id])
        self.admin.reject_waitlisted_users_action(request, queryset)

        # Verify no memberships were created
        self.assertFalse(
            SessionMembership.objects.filter(user=user1, session=self.session).exists()
        )
        self.assertFalse(
            SessionMembership.objects.filter(user=user2, session=self.session).exists()
        )

        # Verify users were removed from waitlist
        self.assertFalse(Waitlist.objects.filter(user=user1).exists())
        self.assertFalse(Waitlist.objects.filter(user=user2).exists())

        # Verify emails were sent
        self.assertEqual(mock_send.call_count, 2)


class SessionMembershipAdminActionsTests(TestCase):
    """Tests for SessionMembershipAdmin admin actions."""

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.admin = SessionMembershipAdmin(SessionMembership, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com",
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_superuser=True,
        )
        self.session = SessionFactory.create(title="Test Session", slug="test-session")

    def _get_request(self):
        """Create a request with session and messages support."""
        request = self.factory.post("/admin/home/sessionmembership/")
        request.user = self.superuser

        # Add session support
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        # Add messages support
        messages = FallbackStorage(request)
        setattr(request, "_messages", messages)

        return request

    @patch("home.views.session_notifications.email.send")
    def test_send_acceptance_emails_action(self, mock_send):
        """Test the send_acceptance_emails_action admin action."""
        # Create memberships
        user1 = UserFactory.create(
            email="user1@example.com", first_name="User", last_name="One"
        )
        user2 = UserFactory.create(
            email="user2@example.com", first_name="User", last_name="Two"
        )
        membership1 = SessionMembershipFactory.create(
            user=user1,
            session=self.session,
            role=SessionMembership.DJANGONAUT,
            accepted=None,
        )
        membership2 = SessionMembershipFactory.create(
            user=user2,
            session=self.session,
            role=SessionMembership.DJANGONAUT,
            accepted=None,
        )

        # Execute the action
        request = self._get_request()
        queryset = SessionMembership.objects.filter(
            id__in=[membership1.id, membership2.id]
        )
        self.admin.send_acceptance_emails_action(request, queryset)

        # Verify emails were sent
        self.assertEqual(mock_send.call_count, 2)

    @patch("home.views.session_notifications.email.send")
    def test_send_acceptance_emails_action_filters_djangonauts_only(self, mock_send):
        """Test that only Djangonauts receive acceptance emails."""
        # Create different role memberships
        djangonaut = UserFactory.create(email="djangonaut@example.com")
        navigator = UserFactory.create(email="navigator@example.com")
        captain = UserFactory.create(email="captain@example.com")

        djangonaut_membership = SessionMembershipFactory.create(
            user=djangonaut,
            session=self.session,
            role=SessionMembership.DJANGONAUT,
            accepted=None,
        )
        navigator_membership = SessionMembershipFactory.create(
            user=navigator,
            session=self.session,
            role=SessionMembership.NAVIGATOR,
            accepted=None,
        )
        captain_membership = SessionMembershipFactory.create(
            user=captain,
            session=self.session,
            role=SessionMembership.CAPTAIN,
            accepted=None,
        )

        # Execute the action on all memberships
        request = self._get_request()
        queryset = SessionMembership.objects.filter(
            id__in=[
                djangonaut_membership.id,
                navigator_membership.id,
                captain_membership.id,
            ]
        )
        self.admin.send_acceptance_emails_action(request, queryset)

        # Only one email should be sent (to the Djangonaut)
        self.assertEqual(mock_send.call_count, 1)
