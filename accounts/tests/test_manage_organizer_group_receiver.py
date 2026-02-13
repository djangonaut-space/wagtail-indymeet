from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from accounts.models import CustomUser
from home.models.session import Session, SessionMembership


class TestManageOrganizerGroupReceiver(TestCase):
    def test_past_session_organizer_not_granted_permissions(self):
        """
        Test that organizers of past sessions are NOT granted permissions.
        """
        # Create a user
        user = CustomUser.objects.create_user(
            username="testuser", email="test@example.com", password="password"
        )

        # Create a PAST session
        today = timezone.now().date()
        # Start and end in the past
        past_start = today - timedelta(days=60)
        past_end = today - timedelta(days=30)

        session = Session.objects.create(
            title="Past Session",
            start_date=past_start,
            end_date=past_end,
            slug="past-session",
            invitation_date=past_start - timedelta(days=10),
            application_start_date=past_start - timedelta(days=20),
            application_end_date=past_start - timedelta(days=15),
        )

        # Verify session status is 'past'
        self.assertEqual(session.status, "past")

        # Add user as ORGANIZER to the session
        # This triggers the receiver
        SessionMembership.objects.create(
            user=user, session=session, role=SessionMembership.ORGANIZER
        )

        # Refresh user from db
        user.refresh_from_db()

        self.assertFalse(user.is_staff)
        self.assertFalse(user.groups.filter(name="Session Organizers").exists())
