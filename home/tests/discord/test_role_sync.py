"""
Tests for the guild role mirror (home.services.discord_roles) against the
stubbed Discord API in ``home.tests.discord.stubs``.
"""

from io import StringIO

import responses as rsps
from django.core.management import CommandError, call_command
from django.test import TestCase

from accounts.factories import DiscordRoleFactory
from accounts.models import DiscordRole
from home.services.discord_roles import sync_discord_roles
from home.tests.discord.stubs import stub_discord_api


class SyncDiscordRolesTests(TestCase):
    @rsps.activate
    def test_mirrors_guild_roles(self):
        stub_discord_api()

        report = sync_discord_roles()

        self.assertEqual(
            set(DiscordRole.objects.values_list("name", "discord_id")),
            {
                ("Djangonaut Bot", "r-bot"),
                ("Djangonauts", "r-dj"),
                ("Captains", "r-cap"),
                ("Navigators", "r-nav"),
                ("Session Organizers", "r-org"),
                ("Admins", "r-adm"),
                ("Advisors", "r-adv"),
            },
        )
        self.assertNotIn("@everyone", report.synced)
        self.assertEqual(report.removed, [])

    @rsps.activate
    def test_skips_integration_managed_roles(self):
        """Bot roles are Discord's to manage and nobody announces to a bot."""
        stub_discord_api(
            roles=[
                {"id": "r-dj", "name": "Djangonauts"},
                {"id": "r-int", "name": "Some Bot", "managed": True},
            ]
        )

        sync_discord_roles()

        self.assertEqual(
            list(DiscordRole.objects.values_list("name", flat=True)), ["Djangonauts"]
        )

    @rsps.activate
    def test_renaming_on_discord_updates_the_row(self):
        DiscordRoleFactory(name="Djangonaughts", discord_id="r-dj")
        stub_discord_api(roles=[{"id": "r-dj", "name": "Djangonauts"}])

        sync_discord_roles()

        role = DiscordRole.objects.get()
        self.assertEqual(role.name, "Djangonauts")
        self.assertEqual(role.discord_id, "r-dj")

    @rsps.activate
    def test_removes_roles_deleted_from_the_guild(self):
        """A mention resolving to a dead id would post as unreadable noise."""
        DiscordRoleFactory(name="Team Pluto", discord_id="r-pluto")
        stub_discord_api(roles=[{"id": "r-dj", "name": "Djangonauts"}])

        report = sync_discord_roles()

        self.assertEqual(report.removed, ["Team Pluto"])
        self.assertEqual(
            list(DiscordRole.objects.values_list("name", flat=True)), ["Djangonauts"]
        )

    @rsps.activate
    def test_rerun_is_idempotent(self):
        stub_discord_api()

        sync_discord_roles()
        first = set(DiscordRole.objects.values_list("discord_id", flat=True))
        report = sync_discord_roles()

        self.assertEqual(
            set(DiscordRole.objects.values_list("discord_id", flat=True)), first
        )
        self.assertEqual(report.removed, [])

    @rsps.activate
    def test_collapses_duplicate_names(self):
        """Discord allows two roles to share a name; a mention cannot pick one."""
        stub_discord_api(
            roles=[
                {"id": "r-dj", "name": "Djangonauts"},
                {"id": "r-dj-2", "name": "djangonauts"},
            ]
        )

        sync_discord_roles()

        self.assertEqual(
            list(DiscordRole.objects.values_list("discord_id", flat=True)), ["r-dj"]
        )


class SyncDiscordRolesCommandTests(TestCase):
    @rsps.activate
    def test_syncs(self):
        stub_discord_api(roles=[{"id": "r-dj", "name": "Djangonauts"}])

        call_command("sync_discord_roles", stdout=StringIO())

        self.assertEqual(DiscordRole.objects.count(), 1)

    def test_requires_discord_credentials(self):
        with self.settings(DISCORD_BOT_TOKEN=""):
            with self.assertRaises(CommandError):
                call_command("sync_discord_roles")

        self.assertEqual(len(rsps.calls), 0)
