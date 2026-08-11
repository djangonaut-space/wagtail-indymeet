"""Tests for DiscordMember sync and legacy username backfill."""

import responses as rsps
from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.factories import UserFactory
from home.factories import DiscordMemberFactory
from home.models import DiscordMember
from home.services.discord_members import apply_username_links, sync_discord_members
from home.tests.discord.stubs import GUILD_ID, member, stub_discord_api


@override_settings(DISCORD_GUILD_ID=GUILD_ID, DISCORD_BOT_TOKEN="token")
class SyncDiscordMembersTests(TestCase):
    @rsps.activate
    def test_upserts_members_and_deactivates_missing(self):
        DiscordMemberFactory.create(discord_id="gone", username="gone", is_active=True)
        stub_discord_api(
            guild_members=[
                member("100", "novauser1", roles=["r-dj"]),
                {
                    "user": {"id": "101", "username": "botty", "bot": True},
                    "roles": [],
                    "nick": None,
                },
            ]
        )

        report = sync_discord_members()

        self.assertEqual(report.synced, 2)
        self.assertEqual(report.deactivated, 1)
        active = DiscordMember.objects.get(discord_id="100")
        self.assertEqual(active.username, "novauser1")
        self.assertEqual(active.role_ids, ["r-dj"])
        self.assertTrue(active.is_active)
        bot = DiscordMember.objects.get(discord_id="101")
        self.assertTrue(bot.is_bot)
        self.assertFalse(DiscordMember.objects.get(discord_id="gone").is_active)

    @rsps.activate
    def test_apply_links_only_unique_active_matches(self):
        DiscordMemberFactory.create(discord_id="100", username="unique")
        DiscordMemberFactory.create(discord_id="101", username="dupe")
        DiscordMemberFactory.create(discord_id="102", username="dupe")
        profile = UserFactory.create(profile__discord_username="unique").profile
        conflict = UserFactory.create(profile__discord_username="dupe").profile
        missing = UserFactory.create(profile__discord_username="absent").profile

        report = apply_username_links()

        profile.refresh_from_db()
        conflict.refresh_from_db()
        missing.refresh_from_db()
        self.assertEqual(profile.discord_member.discord_id, "100")
        self.assertIsNone(conflict.discord_member)
        self.assertIsNone(missing.discord_member)
        self.assertEqual(len(report.linked), 1)
        self.assertEqual(len(report.skipped), 2)

    @rsps.activate
    def test_management_command_syncs(self):
        stub_discord_api(guild_members=[member("100", "novauser1")])
        call_command("sync_discord_members")
        self.assertEqual(DiscordMember.objects.count(), 1)
