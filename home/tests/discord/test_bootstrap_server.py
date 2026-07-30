"""Tests for the ``bootstrap_discord_server`` management command."""

from io import StringIO

import responses
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from home.integrations.discord.session_service import (
    PAST_DISCORD_ROLES,
    STANDING_ROLES,
)
from home.tests.discord.stubs import (
    STANDING_GUILD_ROLES,
    role_creations,
    stub_discord_api,
)

ALUMNI_ROLES = tuple(PAST_DISCORD_ROLES.values())


@override_settings(ENVIRONMENT="dev")
class BootstrapDiscordServerTests(TestCase):
    def _run(self, *args, roles=None, **kwargs):
        stdout = StringIO()
        stub_discord_api(roles=roles)
        call_command("bootstrap_discord_server", *args, stdout=stdout, **kwargs)
        return stdout.getvalue()

    @responses.activate
    def test_creates_standing_and_alumni_roles_on_empty_server(self):
        # Only @everyone exists on a fresh server.
        output = self._run(roles=[{"id": "guild-1", "name": "@everyone"}])

        expected = list(STANDING_ROLES) + list(ALUMNI_ROLES)
        self.assertEqual(role_creations(), expected)
        self.assertIn("role(s) created", output)

    @responses.activate
    def test_idempotent_when_standing_roles_already_exist(self):
        # STANDING_GUILD_ROLES already has all six standing roles; only the
        # alumni roles should be created.
        self._run(roles=STANDING_GUILD_ROLES)

        self.assertEqual(role_creations(), list(ALUMNI_ROLES))

    @responses.activate
    def test_role_match_is_case_insensitive(self):
        roles = [
            {"id": "guild-1", "name": "@everyone"},
            {"id": "r-dj", "name": "djangonauts"},  # different case
        ]
        self._run(roles=roles)

        self.assertNotIn("Djangonauts", role_creations())

    @override_settings(ENVIRONMENT="production")
    def test_refuses_outside_dev_environment(self):
        with self.assertRaises(CommandError):
            call_command("bootstrap_discord_server", stdout=StringIO())

    @override_settings(DISCORD_GUILD_ID="")
    def test_errors_without_guild_configured(self):
        with self.assertRaises(CommandError):
            call_command("bootstrap_discord_server", stdout=StringIO())
