from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from accounts.factories import UserFactory
from home.factories import SessionFactory, SessionMembershipFactory
from home.models import SessionMembership


class TestManageOrganizerGroupReceiver(TestCase):
    def test_past_session_organizer_not_granted_permissions(self):
        """
        Test that organizers of past sessions are NOT granted permissions.
        """
        user = UserFactory.create()

        today = timezone.now().date()
        past_start = today - timedelta(days=60)
        past_end = today - timedelta(days=30)

        session = SessionFactory.create(
            start_date=past_start,
            end_date=past_end,
            invitation_date=past_start - timedelta(days=10),
            application_start_date=past_start - timedelta(days=20),
            application_end_date=past_start - timedelta(days=15),
        )

        self.assertEqual(session.status, "past")

        SessionMembershipFactory.create(
            user=user, session=session, role=SessionMembership.ORGANIZER
        )

        user.refresh_from_db()

        self.assertFalse(user.is_staff)
        self.assertFalse(user.groups.filter(name="Session Organizers").exists())
