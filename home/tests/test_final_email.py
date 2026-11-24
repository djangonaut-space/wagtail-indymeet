"""Tests for the end of session email and its certificate."""

import datetime
import threading
import time

import time_machine
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.db import connection, connections
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.factories import UserFactory
from home import constants, preview_email
from home.admin import SessionMembershipAdmin
from home.factories import (
    OrganizerFactory,
    SessionFactory,
    SessionMembershipFactory,
)
from home.models import Session, SessionMembership, SessionMembershipNotification
from home.tasks.session_notifications import (
    schedule_exit_survey_reminders,
    schedule_final_emails,
    send_final_email,
)

END_DATE = datetime.date(2026, 11, 23)


@override_settings(ENVIRONMENT="production")
class SendFinalEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(
            end_date=END_DATE, exit_survey_url="https://example.com/exit-survey"
        )
        cls.user = UserFactory.create(
            email="grace@example.com", first_name="Grace", last_name="Hopper"
        )
        cls.membership = SessionMembershipFactory.create(
            session=cls.session, user=cls.user, role=constants.DJANGONAUT
        )

    def test_sends(self):
        send_final_email.call(membership_id=self.membership.pk)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["grace@example.com"])
        self.assertIn("Dear Grace,", message.body)
        self.assertIn("https://example.com/exit-survey", message.body)
        filename, content, mimetype = message.attachments[0]
        self.assertEqual(
            filename, "DjangonautSpaceCertificate_GraceHopper_20261123.pdf"
        )
        self.assertEqual(mimetype, "application/pdf")
        self.assertTrue(content.startswith(b"%PDF"))
        self.membership.refresh_from_db()
        self.assertIsNotNone(self.membership.notification.final_email_sent_at)

    def test_skips_already_sent(self):
        SessionMembershipNotification.objects.create(
            session_membership=self.membership, final_email_sent_at=timezone.now()
        )
        send_final_email.call(membership_id=self.membership.pk)
        self.assertEqual(mail.outbox, [])

    def test_without_survey_url(self):
        """The exit survey bullet is left out rather than showing an empty link."""
        Session.objects.filter(pk=self.session.pk).update(exit_survey_url="")
        send_final_email.call(membership_id=self.membership.pk)
        self.assertNotIn("Mission Debrief", mail.outbox[0].body)


@override_settings(ENVIRONMENT="production")
class ScheduleFinalEmailsTests(TestCase):
    def test_only_accepted_djangonauts_of_sessions_ending_today(self):
        today = timezone.now().date()
        ending = SessionFactory.create(end_date=today)
        ended = SessionFactory.create(end_date=today - datetime.timedelta(days=1))
        recipient = SessionMembershipFactory.create(session=ending)
        SessionMembershipFactory.create(session=ending, accepted=False)
        SessionMembershipFactory.create(session=ending, role=constants.CAPTAIN)
        SessionMembershipFactory.create(session=ended)

        schedule_final_emails.call()

        self.assertEqual([m.to for m in mail.outbox], [[recipient.user.email]])

    def test_membership_ids(self):
        """Ids from the admin are sent regardless of the session's end date."""
        ended = SessionFactory.create(end_date=END_DATE)
        recipient = SessionMembershipFactory.create(session=ended)
        SessionMembershipFactory.create(session=ended)

        schedule_final_emails.call(membership_ids=[recipient.pk])

        self.assertEqual([m.to for m in mail.outbox], [[recipient.user.email]])


@override_settings(ENVIRONMENT="production", BASE_URL="https://djangonaut.space")
class ExitSurveyReminderTests(TestCase):
    def setUp(self):
        self.end_date = timezone.now().date() + datetime.timedelta(days=7)

    def test_emails_organizers(self):
        session = SessionFactory.create(end_date=self.end_date)
        organizer = OrganizerFactory.create(session=session)
        SessionMembershipFactory.create(session=session)

        schedule_exit_survey_reminders.call()

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [organizer.user.email])
        self.assertIn(
            f"https://djangonaut.space/django-admin/home/session/{session.pk}/change/",
            message.body,
        )

    def test_skips_sessions_with_survey_url(self):
        session = SessionFactory.create(
            end_date=self.end_date, exit_survey_url="https://example.com/survey"
        )
        OrganizerFactory.create(session=session)
        schedule_exit_survey_reminders.call()
        self.assertEqual(mail.outbox, [])

    def test_skips_sessions_already_emailed(self):
        """Final emails sent early from the admin can't include the link anymore."""
        session = SessionFactory.create(end_date=self.end_date)
        OrganizerFactory.create(session=session)
        SessionMembershipNotification.objects.create(
            session_membership=SessionMembershipFactory.create(session=session),
            final_email_sent_at=timezone.now(),
        )
        schedule_exit_survey_reminders.call()
        self.assertEqual(mail.outbox, [])

    def test_only_sessions_ending_in_a_week(self):
        """Matching one date means each session is reminded once, not every day."""
        for days in (6, 8):
            session = SessionFactory.create(
                end_date=self.end_date + datetime.timedelta(days=days - 7)
            )
            OrganizerFactory.create(session=session)
        schedule_exit_survey_reminders.call()
        self.assertEqual(mail.outbox, [])


@override_settings(ENVIRONMENT="production")
class FinalEmailAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(
            email="admin@example.com", is_staff=True, is_superuser=True
        )
        cls.session = SessionFactory.create(end_date=END_DATE)
        cls.sent = SessionMembershipFactory.create(session=cls.session)
        SessionMembershipNotification.objects.create(
            session_membership=cls.sent, final_email_sent_at=timezone.now()
        )
        cls.unsent = SessionMembershipFactory.create(session=cls.session)

    def _request(self):
        request = RequestFactory().post("/admin/")
        request.user = self.superuser
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    @time_machine.travel(datetime.date(2026, 12, 1))
    def test_send_page(self):
        """The page says sending is automatic and lists only unsent Djangonauts."""
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("admin:session_send_final_emails", args=[self.session.pk])
        )
        self.assertContains(response, "This doesn't need to be done manually.")
        self.assertContains(response, "were sent automatically on 2026-11-23")
        self.assertContains(response, self.unsent.user.email)
        self.assertNotContains(response, self.sent.user.email)

    @time_machine.travel(datetime.date(2026, 11, 1))
    def test_send_page_before_end_date(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("admin:session_send_final_emails", args=[self.session.pk])
        )
        self.assertContains(response, "are sent automatically on 2026-11-23")

    def test_send_skips_already_sent(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("admin:session_send_final_emails", args=[self.session.pk])
        )
        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        self.assertEqual([m.to for m in mail.outbox], [[self.unsent.user.email]])

    def test_resend(self):
        admin = SessionMembershipAdmin(SessionMembership, AdminSite())
        admin.resend_final_email_action(
            self._request(), SessionMembership.objects.filter(pk=self.sent.pk)
        )
        self.assertEqual([m.to for m in mail.outbox], [[self.sent.user.email]])

    def test_preview(self):
        """The preview goes to the admin and doesn't count as the member's email."""
        preview_email.final_email_action(
            SessionMembershipAdmin(SessionMembership, AdminSite()),
            self._request(),
            SessionMembership.objects.filter(pk=self.unsent.pk),
        )
        self.assertEqual([m.to for m in mail.outbox], [["admin@example.com"]])
        self.assertFalse(
            SessionMembershipNotification.objects.filter(
                session_membership=self.unsent
            ).exists()
        )


@override_settings(ENVIRONMENT="production")
class SendFinalEmailLockTests(TransactionTestCase):
    """Uses real transactions so a second connection can hold the row lock."""

    def setUp(self):
        self.membership = SessionMembershipFactory.create(
            session=SessionFactory.create(end_date=END_DATE)
        )
        self.notification = SessionMembershipNotification.objects.create(
            session_membership=self.membership
        )
        self.other_connection = connection.copy()
        self.other_connection.set_autocommit(False)

    def tearDown(self):
        self.other_connection.rollback()
        self.other_connection.close()

    def _wait_for_blocked_query(self) -> None:
        """Wait until a query in the database is waiting on a lock."""
        deadline = time.monotonic() + 10
        with connection.cursor() as cursor:
            while time.monotonic() < deadline:
                cursor.execute("SELECT count(*) FROM pg_locks WHERE NOT granted")
                if cursor.fetchone()[0]:
                    return
                time.sleep(0.01)
        self.fail("send_final_email never waited on the row lock")

    def test_waits_for_concurrent_send(self):
        """A send that's blocked by another sees its timestamp and doesn't email again."""
        table = SessionMembershipNotification._meta.db_table
        with self.other_connection.cursor() as cursor:
            cursor.execute(
                f"SELECT id FROM {table} WHERE id = %s FOR UPDATE",
                [self.notification.pk],
            )

        def send() -> None:
            try:
                send_final_email.call(membership_id=self.membership.pk)
            finally:
                connections.close_all()

        thread = threading.Thread(target=send)
        thread.start()
        self._wait_for_blocked_query()

        with self.other_connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET final_email_sent_at = now() WHERE id = %s",
                [self.notification.pk],
            )
        self.other_connection.commit()
        thread.join()

        self.assertEqual(mail.outbox, [])
