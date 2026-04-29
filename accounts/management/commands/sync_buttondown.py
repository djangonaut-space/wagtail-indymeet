from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from home.integrations.buttondown.service import buttondown_enabled
from home.tasks.sync_buttondown import sync_user_to_buttondown

User = get_user_model()


class Command(BaseCommand):
    help = "Enqueue a Buttondown sync task for every active user."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List users that would be synced without enqueueing tasks.",
        )

    def handle(self, *args, **options) -> None:
        if not buttondown_enabled():
            self.stderr.write(
                self.style.ERROR("BUTTONDOWN_API_KEY is not set; aborting.")
            )
            return

        dry_run = options["dry_run"]
        count = 0

        for user in User.objects.filter(is_active=True).iterator():
            if dry_run:
                self.stdout.write(f"Would sync: {user.email} (pk={user.pk})")
            else:
                sync_user_to_buttondown.enqueue(user.pk)
            count += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run complete: {count} user(s) would be synced."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Enqueued Buttondown sync for {count} user(s).")
            )
