"""Tests for availability template tags."""

from django.test import TestCase

from accounts.factories import UserFactory
from home.templatetags.availability_tags import admin_unavailable_url


class AdminUnavailableUrlFilterTests(TestCase):
    """Tests for the admin_unavailable_url template filter."""

    def test_uses_user_ids(self):
        """Test that admin_unavailable_url uses user.id, not str(user)."""
        user1 = UserFactory(username="user1", email="user1@example.com")
        user2 = UserFactory(username="user2", email="user2@example.com")

        url = admin_unavailable_url([user1.id, user2.id])

        expected_ids = f"{user1.id},{user2.id}"
        self.assertIn(f"?user_id__in={expected_ids}", url)
        self.assertIn("home/sessionmembership/", url)

    def test_returns_none_when_no_unavailable_ids(self):
        """Test that admin_unavailable_url returns None with no unavailable ids."""
        self.assertIsNone(admin_unavailable_url([]))
