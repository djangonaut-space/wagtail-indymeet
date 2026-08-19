"""
Tests for the DiscordMember export resource and the UserProfile
import/export resource's discord_username <-> discord_member linking.
"""

import tablib
from django.test import TestCase

from accounts.admin import DiscordMemberResource, UserProfileResource
from accounts.factories import DiscordMemberFactory, UserFactory
from accounts.models import DiscordMember, UserProfile


class DiscordMemberResourceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = DiscordMemberFactory.create(
            discord_id="100", username="novauser1", nickname="Nova"
        )

    def test_export_includes_model_fields(self):
        dataset = DiscordMemberResource().export(DiscordMember.objects.all())

        row = dataset.dict[0]
        self.assertEqual(row["username"], "novauser1")
        self.assertEqual(row["nickname"], "Nova")
        self.assertEqual(row["discord_id"], "100")
        self.assertEqual(row["display_name"], "Nova")


class UserProfileResourceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create(username="djangonaut")
        cls.profile = cls.user.profile
        cls.member = DiscordMemberFactory.create(discord_id="200", username="novauser2")

    def test_export_renders_discord_username_from_linked_member(self):
        self.profile.discord_member = self.member
        self.profile.save(update_fields=["discord_member"])

        dataset = UserProfileResource().export(
            UserProfile.objects.filter(pk=self.profile.pk)
        )

        row = dataset.dict[0]
        self.assertEqual(dataset.headers, ["id", "user", "discord_username"])
        self.assertEqual(row["discord_username"], "novauser2")

    def test_import_assigns_discord_member_by_username(self):
        dataset = tablib.Dataset(
            [str(self.profile.pk), "novauser2"],
            headers=["id", "discord_username"],
        )

        result = UserProfileResource().import_data(dataset, raise_errors=True)

        self.assertFalse(result.has_errors())
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.discord_member, self.member)

    def test_import_blank_discord_username_leaves_member_unset(self):
        dataset = tablib.Dataset(
            [str(self.profile.pk), ""],
            headers=["id", "discord_username"],
        )

        result = UserProfileResource().import_data(dataset, raise_errors=True)

        self.assertFalse(result.has_errors())
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.discord_member)
