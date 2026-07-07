"""
Management command to bootstrap a Discord server for session management.

The session setup action (``home.integrations.discord.session_service``) looks
up a set of *standing* roles by name and refuses to run when any are missing,
rather than creating them. That makes it awkward to try the Discord
integration against a throwaway server for local development: the roles have to
exist first, and creating them by hand (with the exact names the code expects)
is tedious and error prone.

This command creates those roles -- plus the alumni roles teardown would
otherwise create on first run -- on the configured ``DISCORD_GUILD_ID`` so the
setup and teardown flows can be exercised end to end against a test server. It
refuses to run outside the ``dev`` environment so it can never touch the
production server, and it is idempotent: roles that already exist (matched
case-insensitively, the same way the session actions match them) are skipped.
"""

import requests
from django.conf import settings
from django.core.management import BaseCommand, CommandError

from home.integrations.discord.service import discord_client
from home.integrations.discord.session_service import (
    PAST_DISCORD_ROLES,
    STANDING_ROLES,
)

# Standing roles setup requires, plus the alumni roles teardown creates on
# first run. Seeding the alumni roles up front lets a test server exercise
# teardown without new roles appearing as a side effect.
ROLES_TO_CREATE = tuple(STANDING_ROLES) + tuple(PAST_DISCORD_ROLES.values())


class Command(BaseCommand):
    help = (
        "Create the standing Discord roles the session setup/teardown actions "
        "require on the configured DISCORD_GUILD_ID, so a test server can be "
        "used for local development. Only runs in the dev environment. "
        "Idempotent."
    )

    def handle(self, *args, **options) -> None:
        if getattr(settings, "ENVIRONMENT", None) != "dev":
            raise CommandError(
                "bootstrap_discord_server only runs in the dev environment "
                "(ENVIRONMENT == 'dev') so it can't reconfigure a real server."
            )

        guild_id = getattr(settings, "DISCORD_GUILD_ID", "")
        if not getattr(settings, "DISCORD_BOT_TOKEN", "") or not guild_id:
            raise CommandError(
                "DISCORD_BOT_TOKEN / DISCORD_GUILD_ID are not configured; set "
                "them to your test server before running this command."
            )

        try:
            existing_roles = discord_client.get_guild_roles(guild_id=guild_id)
        except requests.HTTPError as exc:
            raise CommandError(
                f"Could not read roles for guild {guild_id}; check the guild id, "
                "the bot token, and that the bot is a member of the server. "
                f"({exc})"
            ) from exc

        existing_names = {role["name"].casefold() for role in existing_roles}

        created: list[str] = []
        skipped: list[str] = []
        for name in ROLES_TO_CREATE:
            if name.casefold() in existing_names:
                skipped.append(name)
                self.stdout.write(f"Role '{name}' already exists; skipping.")
                continue
            try:
                discord_client.create_guild_role(guild_id=guild_id, name=name)
            except requests.HTTPError as exc:
                raise CommandError(
                    f"Failed to create role '{name}' on guild {guild_id}. Ensure "
                    "the bot has the Manage Roles permission. "
                    f"({exc})"
                ) from exc
            existing_names.add(name.casefold())
            created.append(name)
            self.stdout.write(self.style.SUCCESS(f"Created role '{name}'."))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {len(created)} role(s) created, {len(skipped)} already "
                f"present on guild {guild_id}."
            )
        )
        self.stdout.write(
            "Next steps for a test server:\n"
            "  - Move the bot's role above every role it manages (these roles, "
            "plus per-team and session-title roles) or role edits 403.\n"
            "  - Enable the Server Members Intent on the bot so teardown can list "
            "members.\n"
            "  - Set participants' Discord usernames on their profiles so they "
            "resolve to guild members."
        )
