from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from accounts.factories import UserFactory
from home.factories import SessionFactory, SessionMembershipFactory
from home.models.session import SessionMembership


class OrganizerReceiversHandlersTestCase(TestCase):
    """Tests for receivers that manage organizer group membership."""

    def setUp(self):
        call_command("setup_session_organizers_group")
        self.group = Group.objects.get(name="Session Organizers")

    def test_adds_regular_user_to_group_when_organizer_created(self):
        """Test that creating organizer membership adds user to group."""
        user = UserFactory(is_staff=False, is_superuser=False)
        session = SessionFactory()

        SessionMembershipFactory(
            user=user, session=session, role=SessionMembership.ORGANIZER
        )

        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertIn(self.group, user.groups.all())

    def test_makes_user_staff_when_organizer_created(self):
        """Test that creating organizer membership makes user staff."""
        user = UserFactory(is_staff=False, is_superuser=False)
        session = SessionFactory()

        SessionMembershipFactory(
            user=user, session=session, role=SessionMembership.ORGANIZER
        )

        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_skips_superuser(self):
        """Test that superusers are not added to group."""
        user = UserFactory(is_staff=True, is_superuser=True)
        session = SessionFactory()

        SessionMembershipFactory(
            user=user, session=session, role=SessionMembership.ORGANIZER
        )

        user.refresh_from_db()
        self.assertNotIn(self.group, user.groups.all())

    def test_signal_is_idempotent(self):
        """Test that saving membership multiple times doesn't cause issues."""
        user = UserFactory(is_staff=False, is_superuser=False)
        session = SessionFactory()

        membership = SessionMembershipFactory(
            user=user, session=session, role=SessionMembership.ORGANIZER
        )

        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertIn(self.group, user.groups.all())

        membership.save()

        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertEqual(user.groups.filter(name="Session Organizers").count(), 1)

    def test_does_not_add_non_organizer_to_group(self):
        """Test that non-organizer roles don't add user to group."""
        user = UserFactory(is_staff=False, is_superuser=False)
        session = SessionFactory()

        SessionMembershipFactory(
            user=user, session=session, role=SessionMembership.DJANGONAUT
        )

        user.refresh_from_db()
        self.assertNotIn(self.group, user.groups.all())
        self.assertFalse(user.is_staff)
