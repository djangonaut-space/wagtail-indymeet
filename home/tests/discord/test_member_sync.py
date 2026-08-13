"""Tests for the DiscordMember sync."""

import responses as rsps
from django.core.management import call_command
from django.test import TestCase, override_settings

from home.factories import DiscordMemberFactory
from home.models import DiscordMember
from home.services.discord_members import sync_discord_members
from home.tests.discord.stubs import GUILD_ID, member, stub_discord_api


@override_settings(DISCORD_GUILD_ID=GUILD_ID, DISCORD_BOT_TOKEN="token")
class SyncDiscordMembersTests(TestCase):
    @rsps.activate
    def test_upserts_members_and_leaves_absentees(self):
        gone = DiscordMemberFactory.create(discord_id="gone", username="gone")
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
        active = DiscordMember.objects.get(discord_id="100")
        self.assertEqual(active.username, "novauser1")
        self.assertEqual(active.role_ids, ["r-dj"])
        self.assertTrue(DiscordMember.objects.filter(discord_id="101").exists())
        # Members no longer in the guild are left untouched, not deleted.
        gone.refresh_from_db()
        self.assertEqual(gone.username, "gone")

    @rsps.activate
    def test_skips_members_with_no_changes(self):
        DiscordMemberFactory.create(
            discord_id="100", username="novauser1", nickname="", role_ids=["r-dj"]
        )
        stub_discord_api(guild_members=[member("100", "novauser1", roles=["r-dj"])])

        with self.assertNumQueries(1):
            report = sync_discord_members()

        self.assertEqual(report.synced, 1)

    @rsps.activate
    def test_management_command_syncs(self):
        stub_discord_api(guild_members=[member("100", "novauser1")])
        call_command("sync_discord_members")
        self.assertEqual(DiscordMember.objects.count(), 1)
