from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX
from django.contrib.auth.tokens import default_token_generator
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from home.email import send

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Email active users with unusable passwords to inform them that an account "
        "exists for their email address and explain how to set a password or delete "
        "their account."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List affected users without sending any emails.",
        )

    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]
        users = User.objects.filter(
            is_active=True,
            password__startswith=UNUSABLE_PASSWORD_PREFIX,
        ).iterator()
        emails_sent = 0

        for user in users:
            if dry_run:
                self.stdout.write(
                    f"Would email: {user.email} ({user.get_full_name() or user.username})"
                )
                emails_sent += 1
                continue

            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_path = reverse(
                "password_reset_confirm",
                kwargs={"uidb64": uidb64, "token": token},
            )
            send(
                email_template="unusable_password_notification",
                recipient_list=[user.email],
                context={
                    "name": user.get_full_name() or user.username,
                    "cta_link": settings.BASE_URL + reset_path,
                    "delete_account_url": settings.BASE_URL + reverse("delete_account"),
                },
            )
            emails_sent += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run complete: {emails_sent} user(s) would be notified."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"Notified {emails_sent} user(s)."))
