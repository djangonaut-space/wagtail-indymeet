from datetime import datetime
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from freezegun import freeze_time

from accounts.factories import UserFactory
from home.factories import SessionFactory


class ApplicationOpenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.session_application = SessionFactory.create(
            application_start_date=datetime(2023, 10, 16).date(),
            application_end_date=datetime(2023, 11, 15).date(),
            start_date=datetime(2023, 12, 15).date(),
            end_date=datetime(2023, 12, 30).date(),
            title="Test Session",
            slug="test-session",
            application_url="https://example.com",
        )
        cls.user_1_with_notifications = UserFactory.create(
            email="notify@me1.com",
            profile__email_confirmed=True,
            profile__receiving_program_updates=True,
        )
        cls.user_2_with_notifications = UserFactory.create(
            email="notify@me2.com",
            profile__email_confirmed=True,
            profile__receiving_program_updates=True,
        )
        cls.user_without_notifications = UserFactory.create(
            email="go@away.com",
            profile__email_confirmed=True,
            profile__receiving_program_updates=False,
        )

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "applications_open_email",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()

    @freeze_time("2023-11-16")
    def test_no_emails_sent_when_not_application_open_date(self):
        out = self.call_command()
        self.assertIn("There are no sessions with applications starting today", out)

    @freeze_time("2023-10-16")
    def test_emails_sent_when_application_open_date(self):
        out = self.call_command()
        self.assertIn(
            "Application open notification sent to 2 prospective Djangonauts for session 'Test Session'!",
            out,
        )
        self.assertEqual(len(mail.outbox), 2)
        recipients = [*mail.outbox[0].recipients(), *mail.outbox[1].recipients()]
        self.assertEqual(
            recipients,
            [
                self.user_1_with_notifications.email,
                self.user_2_with_notifications.email,
            ],
        )
        self.assertEqual(
            {mail.outbox[0].subject, mail.outbox[1].subject},
            {"Djangonaut Space Program Applications Open"},
        )
        # Check the contents of an email
        self.assertIn(
            self.session_application.application_url,
            mail.outbox[0].body,
        )
        self.assertIn(
            self.session_application.get_full_url(),
            mail.outbox[0].body,
        )
        self.assertIn(
            "This session runs from Dec 15, 2023 - Dec 30, 2023 and applications close Nov 15, 2023.",
            mail.outbox[0].body,
        )
