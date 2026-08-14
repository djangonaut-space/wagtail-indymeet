"""
Tests for UserProfile admin Discord member linking.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.factories import DiscordMemberFactory, UserFactory


class UserProfileChangelistTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = UserFactory.create(
            username="admin", is_staff=True, is_superuser=True
        )
        cls.user = UserFactory.create(username="djangonaut")
        cls.profile = cls.user.profile
        cls.member = DiscordMemberFactory.create(discord_id="100", username="novauser1")

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_changelist_shows_discord_member(self):
        self.profile.discord_member = self.member
        self.profile.save(update_fields=["discord_member"])
        url = reverse("admin:accounts_userprofile_changelist")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "novauser1")

    def test_change_form_includes_discord_member(self):
        url = reverse("admin:accounts_userprofile_change", args=[self.profile.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "discord_member")
