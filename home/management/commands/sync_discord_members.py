"""Refresh the local mirror of the Discord server's members."""

import requests
from django.conf import settings
from django.core.management import BaseCommand, CommandError

from home.services.discord_members import apply_username_links, sync_discord_members


class Command(BaseCommand):
    help = (
        "Refresh the local DiscordMember mirror from DISCORD_GUILD_ID. "
        "Optionally backfill UserProfile.discord_member from legacy "
        "discord_username values."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply-links",
            action="store_true",
            help=(
                "After syncing, link profiles whose discord_username uniquely "
                "matches one active non-bot guild member."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="With --apply-links, report matches without writing links.",
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
            self.style.SUCCESS(
                f"Done: {report.synced} member(s) mirrored, "
                f"{report.deactivated} deactivated."
            )
        )

        if not options["apply_links"]:
            return

        links = apply_username_links(dry_run=options["dry_run"])
        prefix = "Would link" if options["dry_run"] else "Linked"
        for label in links.linked:
            self.stdout.write(f"{prefix}: {label}")
        for label in links.skipped:
            self.stdout.write(f"Skipped (no unique match): {label}")
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix} {len(links.linked)}; skipped {len(links.skipped)}."
            )
        )
