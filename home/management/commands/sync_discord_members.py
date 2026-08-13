"""Refresh the local mirror of the Discord server's members."""

import requests
from django.conf import settings
from django.core.management import BaseCommand, CommandError

from home.services.discord_members import sync_discord_members


class Command(BaseCommand):
    help = (
        "Refresh the local DiscordMember mirror from DISCORD_GUILD_ID. Link "
        "members to user profiles / session memberships in admin."
    )

    def handle(self, *args, **options) -> None:
        if not getattr(settings, "DISCORD_BOT_TOKEN", "") or not getattr(
            settings, "DISCORD_GUILD_ID", ""
        ):
            raise CommandError(
                "DISCORD_BOT_TOKEN / DISCORD_GUILD_ID are not configured; "
                "there is no server to read members from."
            )

        try:
            report = sync_discord_members()
        except requests.HTTPError as exc:
            raise CommandError(
                "Could not read members for guild "
                f"{settings.DISCORD_GUILD_ID}; check the guild id, the bot "
                f"token, GUILD_MEMBERS intent, and that the bot is a member "
                f"of the server. ({exc})"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Done: {report.synced} member(s) mirrored.")
        )
