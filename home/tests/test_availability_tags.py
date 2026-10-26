"""Tests for availability template tags."""

from django.test import RequestFactory, TestCase

from accounts.factories import UserFactory
from home.availability import AvailabilityWindow
from home.slots import Slot
from home.templatetags.availability_tags import unavailable_members_admin_url


class UnavailableMembersAdminUrlTests(TestCase):
    """Tests for the unavailable_members_admin_url template tag."""

    def setUp(self):
        self.factory = RequestFactory()

    def _window(self, unavailable_users):
        return AvailabilityWindow(
            slot_range=(Slot("UTC", 10.0), Slot("UTC", 10.5)),
            formatted_time="Sun 10:00 AM - 11:00 AM",
            available_users=[],
            unavailable_users=unavailable_users,
        )

    def test_uses_unavailable_user_ids(self):
        """Test the URL filters by the ids of the window's unavailable users."""
        user1 = UserFactory(username="user1", email="user1@example.com")
        user2 = UserFactory(username="user2", email="user2@example.com")
        request = self.factory.get("/admin/home/sessionmembership/")

        window = self._window([user1, user2])
        url = unavailable_members_admin_url({"request": request}, window)

        self.assertIn(f"user_id__in={user1.id}%2C{user2.id}", url)
        self.assertIn("home/sessionmembership/", url)

    def test_returns_none_when_no_unavailable_users(self):
        """Test None is returned when the window has no unavailable users."""
        request = self.factory.get("/admin/home/sessionmembership/")

        window = self._window([])
        self.assertIsNone(unavailable_members_admin_url({"request": request}, window))

    def test_carries_over_existing_querystring(self):
        """Test filters already on the request are kept on the new URL.

        This is what keeps a member with memberships in more than one
        session from being shown once per session: whatever filter (session,
        role, etc.) narrowed the admin list before the action ran stays
        applied on the follow-up link.
        """
        user1 = UserFactory(username="user1", email="user1@example.com")
        request = self.factory.get(
            "/admin/home/sessionmembership/?session__id__exact=7&role__exact=captain"
        )

        window = self._window([user1])
        url = unavailable_members_admin_url({"request": request}, window)

        self.assertIn("session__id__exact=7", url)
        self.assertIn("role__exact=captain", url)
        self.assertIn(f"user_id__in={user1.id}", url)

    def test_overrides_existing_user_id_filter(self):
        """Test a stale user_id__in on the request is replaced, not merged."""
        user1 = UserFactory(username="user1", email="user1@example.com")
        request = self.factory.get("/admin/home/sessionmembership/?user_id__in=999")

        window = self._window([user1])
        url = unavailable_members_admin_url({"request": request}, window)

        self.assertIn(f"user_id__in={user1.id}", url)
        self.assertNotIn("999", url)
