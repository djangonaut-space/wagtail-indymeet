"""
Management command to refresh the local mirror of the Discord server's roles.

The mirror (``accounts.models.DiscordRole``) is what lets an announcement say
``@Djangonauts`` and have it ping — see ``home.integrations.discord.service``.
The Discord session setup action refreshes it as its last step, which covers
the normal case, but roles also get added or renamed between sessions. This
command is how that gets picked up without running a full setup.

Idempotent: it rewrites the mirror to match the guild every time.
"""

import requests
from django.conf import settings
from django.core.management import BaseCommand, CommandError

from home.services.discord_roles import sync_discord_roles


class Command(BaseCommand):
    help = (
        "Refresh the local DiscordRole mirror from the configured "
        "DISCORD_GUILD_ID, so announcements can ping the server's current "
        "roles by name. Idempotent."
    )

    def handle(self, *args, **options) -> None:
        if not getattr(settings, "DISCORD_BOT_TOKEN", "") or not getattr(
            settings, "DISCORD_GUILD_ID", ""
        ):
            raise CommandError(
                "DISCORD_BOT_TOKEN / DISCORD_GUILD_ID are not configured; "
                "there is no server to read roles from."
            )

        try:
            report = sync_discord_roles()
        except requests.HTTPError as exc:
            raise CommandError(
                "Could not read roles for guild "
                f"{settings.DISCORD_GUILD_ID}; check the guild id, the bot "
                f"token, and that the bot is a member of the server. ({exc})"
            ) from exc

        for name in report.removed:
            self.stdout.write(f"Removed '{name}', no longer on the server.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {len(report.synced)} role(s) mirrored, "
                f"{len(report.removed)} removed."
            )
        )
