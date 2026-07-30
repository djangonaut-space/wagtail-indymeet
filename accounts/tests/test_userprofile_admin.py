"""
Tests for batch-editing Discord usernames on the UserProfile changelist.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.factories import UserFactory


class UserProfileChangelistTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = UserFactory.create(
            username="admin", is_staff=True, is_superuser=True
        )
        cls.user = UserFactory.create(username="djangonaut")
        cls.profile = cls.user.profile

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_changelist_renders_editable_discord_username(self):
        url = reverse("admin:accounts_userprofile_changelist")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="form-0-discord_username"')

    def test_list_editable_saves_discord_username(self):
        url = reverse("admin:accounts_userprofile_changelist")
        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(self.profile.pk),
            "form-0-discord_username": "batch-entered",
            "_save": "Save",
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.discord_username, "batch-entered")
