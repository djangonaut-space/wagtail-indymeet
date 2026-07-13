"""Poll all calendar connections and prune stale cached busy data.

Intended to be run periodically (e.g. from a scheduler / cron). It enqueues a
background sync for every connection -- which also refreshes free/busy data and
renews near-expiry webhook channels -- and prunes busy periods older than the
retention window.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from availability.models import CalendarBusyPeriod, CalendarConnection
from availability.providers import service
from availability.tasks import sync_calendar_connection


class Command(BaseCommand):
    help = "Enqueue a busy-time sync for every calendar connection and prune old data."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be synced/pruned without making changes.",
        )

    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]
        count = 0

        for connection in CalendarConnection.objects.iterator():
            if dry_run:
                self.stdout.write(
                    f"Would sync: {connection.account_label} (pk={connection.pk})"
                )
            else:
                sync_calendar_connection.enqueue(connection.pk)
            count += 1

        if dry_run:
            pruned = CalendarBusyPeriod.objects.ending_before(
                timezone.now() - service.RETENTION
            ).count()
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run complete: {count} connection(s) would sync, "
                    f"{pruned} busy period(s) would be pruned."
                )
            )
        else:
            pruned = service.prune_busy_periods()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Enqueued sync for {count} connection(s); pruned {pruned} "
                    "old busy period(s)."
                )
            )
