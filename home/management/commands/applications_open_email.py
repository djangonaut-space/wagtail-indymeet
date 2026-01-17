from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from home.email import send
from home.models import Session


class Command(BaseCommand):
    help = """
    Checks if applications are open for a program session
    and notify interested folk via email.
    To be ran once a day.
    """

    def handle(self, *args, **options):
        try:
            applications_starting_today = Session.objects.get(
                application_start_date=timezone.now().date()
            )
        except Session.DoesNotExist:
            self.stdout.write(
                self.style.SUCCESS(
                    "There are no sessions with applications starting today"
                )
            )
            return False
        emails_sent = 0
        for user in (
            CustomUser.objects.select_related("profile")
            .filter(
                profile__email_confirmed=True,
                profile__receiving_program_updates=True,
            )
            .iterator()
        ):
            email_context = {
                "title": applications_starting_today.title,
                "detail_url": applications_starting_today.get_full_url(),
                "start_date": applications_starting_today.start_date.strftime(
                    "%b %d, %Y"
                ),
                "end_date": applications_starting_today.end_date.strftime("%b %d, %Y"),
                "application_end_date": applications_starting_today.application_end_date.strftime(
                    "%b %d, %Y"
                ),
                "cta_link": applications_starting_today.get_application_url(),
                "name": user.get_full_name(),
            }
            send(
                email_template="application_open",
                recipient_list=[user.email],
                context=email_context,
            )
            emails_sent += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Application open notification sent to {emails_sent} prospective Djangonauts "
                f"for session '{applications_starting_today.title}'!"
            )
        )
