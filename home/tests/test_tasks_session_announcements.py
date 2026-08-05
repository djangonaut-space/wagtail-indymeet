"""Tests for the session announcement background tasks.

Covers the two scheduled fan-outs, the per-announcement workers, and the
Tuesday-email to following-Monday-post timing the program relies on.
"""

import datetime

import responses as rsps
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from accounts.factories import UserFactory
from home import constants
from home.factories import (
    AnnouncementFactory,
    SessionFactory,
    SessionMembershipFactory,
)
from home.integrations.discord.client import BASE_URL
from home.tasks.session_announcements import (
    email_organizers_for_announcement,
    post_announcement,
    schedule_approval_emails,
    schedule_pending_announcements,
)

DISCORD_SETTINGS = dict(
    DISCORD_BOT_TOKEN="bot-token",
    DISCORD_GUILD_ID="123456789",
)

EMAIL_SETTINGS = dict(
    ENVIRONMENT="production",
    BASE_URL="https://djangonaut.space",
)


def discord_session(**kwargs):
    """A session whose Discord is set up, so its announcements are postable."""
    kwargs.setdefault("discord_category_id", "cat-1")
    kwargs.setdefault("discord_announcements_channel_id", "chan-1")
    return SessionFactory(**kwargs)


@override_settings(**DISCORD_SETTINGS)
class PostAnnouncementTests(TestCase):
    def setUp(self):
        self.session = discord_session()

    @rsps.activate
    def test_posts_message(self):
        """The week header is assembled at post time, not stored on the message."""
        rsps.add(rsps.POST, f"{BASE_URL}/channels/chan-1/messages", json={"id": "1"})
        announcement = AnnouncementFactory(
            session=self.session,
            week_number=3,
            message="Hello team",
            needs_approval=False,
        )

        post_announcement.call(announcement_id=announcement.pk)

        self.assertEqual(
            rsps.calls[0].request.body,
            b'{"content": "**Week 3**\\n\\nHello team"}',
        )
        announcement.refresh_from_db()
        self.assertIsNotNone(announcement.posted_at)

    @rsps.activate
    def test_rerun_does_not_repost(self):
        """posted_at is the idempotency lock, so a duplicate enqueue is a no-op."""
        rsps.add(rsps.POST, f"{BASE_URL}/channels/chan-1/messages", json={"id": "1"})
        announcement = AnnouncementFactory(session=self.session, needs_approval=False)

        post_announcement.call(announcement_id=announcement.pk)
        post_announcement.call(announcement_id=announcement.pk)

        self.assertEqual(len(rsps.calls), 1)

    @rsps.activate
    def test_skips_unapproved(self):
        announcement = AnnouncementFactory(
            session=self.session, needs_approval=True, approved_at=None
        )

        post_announcement.call(announcement_id=announcement.pk)

        self.assertEqual(len(rsps.calls), 0)
        announcement.refresh_from_db()
        self.assertIsNone(announcement.posted_at)

    @rsps.activate
    def test_ignores_post_date(self):
        """The admin action posts on demand, so post_date is not enforced here."""
        rsps.add(rsps.POST, f"{BASE_URL}/channels/chan-1/messages", json={"id": "1"})
        announcement = AnnouncementFactory(
            session=self.session,
            needs_approval=False,
            post_date=timezone.now().date() + datetime.timedelta(days=30),
        )

        post_announcement.call(announcement_id=announcement.pk)

        self.assertEqual(len(rsps.calls), 1)

    def test_missing_announcement(self):
        """A deleted announcement leaves a stale queued task, which must no-op."""
        post_announcement.call(announcement_id=999999)


@override_settings(**DISCORD_SETTINGS)
class PostPendingAnnouncementsTests(TestCase):
    @rsps.activate
    def test_posts_due_and_approved(self):
        rsps.add(rsps.POST, f"{BASE_URL}/channels/chan-1/messages", json={"id": "1"})
        session = discord_session()
        today = timezone.now().date()
        due = AnnouncementFactory(
            session=session, needs_approval=False, post_date=today
        )
        # Excluded: not due yet.
        AnnouncementFactory(
            session=session,
            needs_approval=False,
            post_date=today + datetime.timedelta(days=1),
        )
        # Excluded: still awaiting approval.
        AnnouncementFactory(
            session=session, needs_approval=True, approved_at=None, post_date=today
        )

        schedule_pending_announcements.call()

        self.assertEqual(len(rsps.calls), 1)
        due.refresh_from_db()
        self.assertIsNotNone(due.posted_at)

    @rsps.activate
    def test_skips_inactive_discord(self):
        """A session that was never set up (or was torn down) has nowhere to post."""
        session = SessionFactory(
            discord_category_id="", discord_announcements_channel_id=""
        )
        AnnouncementFactory(
            session=session,
            needs_approval=False,
            post_date=timezone.now().date(),
        )

        schedule_pending_announcements.call()

        self.assertEqual(len(rsps.calls), 0)


@override_settings(**EMAIL_SETTINGS)
class EmailOrganizersForAnnouncementTests(TestCase):
    def setUp(self):
        self.session = discord_session(title="Session 42")
        self.organizer = UserFactory(email="organizer@example.com")
        SessionMembershipFactory(
            session=self.session, user=self.organizer, role=constants.ORGANIZER
        )
        # A non-organizer member who must not be emailed.
        SessionMembershipFactory(
            session=self.session,
            user=UserFactory(email="djangonaut@example.com"),
            role=constants.DJANGONAUT,
        )

    def test_emails_organizers(self):
        """Only organizers are notified, and the mail names the week and links back."""
        announcement = AnnouncementFactory(
            session=self.session,
            week_number=3,
            needs_approval=True,
            approved_at=None,
            post_date=timezone.now().date(),
        )

        email_organizers_for_announcement.call(announcement_id=announcement.pk)

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["organizer@example.com"])
        self.assertIn("Week 3", sent.subject)
        self.assertIn(announcement.post_date.isoformat(), sent.subject)
        self.assertIn(
            reverse("admin:home_announcement_change", args=[announcement.pk]),
            sent.body,
        )
        announcement.refresh_from_db()
        self.assertIsNotNone(announcement.emailed_for_approval_at)

    def test_rerun_does_not_email_again(self):
        """emailed_for_approval_at stops organizers being chased twice."""
        announcement = AnnouncementFactory(
            session=self.session,
            needs_approval=True,
            approved_at=None,
            post_date=timezone.now().date(),
        )

        email_organizers_for_announcement.call(announcement_id=announcement.pk)
        email_organizers_for_announcement.call(announcement_id=announcement.pk)

        self.assertEqual(len(mail.outbox), 1)

    def test_skips_approved(self):
        announcement = AnnouncementFactory(
            session=self.session,
            needs_approval=True,
            approved_at=timezone.now(),
            post_date=timezone.now().date(),
        )

        email_organizers_for_announcement.call(announcement_id=announcement.pk)

        self.assertEqual(len(mail.outbox), 0)

    def test_missing_announcement(self):
        """A deleted announcement leaves a stale queued task, which must no-op."""
        email_organizers_for_announcement.call(announcement_id=999999)

        self.assertEqual(len(mail.outbox), 0)


@override_settings(**EMAIL_SETTINGS)
class EmailAnnouncementsForApprovalTests(TestCase):
    def setUp(self):
        self.session = discord_session()
        SessionMembershipFactory(
            session=self.session,
            user=UserFactory(email="organizer@example.com"),
            role=constants.ORGANIZER,
        )

    def test_skips_inactive_discord(self):
        """A session that was never set up (or was torn down) has nowhere to post."""
        session = SessionFactory(
            discord_category_id="", discord_announcements_channel_id=""
        )
        SessionMembershipFactory(
            session=session,
            user=UserFactory(email="other@example.com"),
            role=constants.ORGANIZER,
        )
        AnnouncementFactory(
            session=session,
            needs_approval=True,
            approved_at=None,
            post_date=timezone.now().date(),
        )

        schedule_approval_emails.call()

        self.assertEqual(len(mail.outbox), 0)


@override_settings(**{**DISCORD_SETTINGS, **EMAIL_SETTINGS})
class WeeklyCadenceTests(TestCase):
    """The Tuesday email must cover exactly the following Monday's posts.

    ``awaiting_approval``'s six day lead time is what ties the two schedules
    together, so it is asserted against real calendar dates rather than
    against the queryset boundary alone.
    """

    def setUp(self):
        self.session = discord_session(
            start_date=datetime.date(2026, 1, 12),
            end_date=datetime.date(2026, 3, 16),
        )
        SessionMembershipFactory(
            session=self.session,
            user=UserFactory(email="organizer@example.com"),
            role=constants.ORGANIZER,
        )

    def test_tuesday_email(self):
        """A Tuesday run reaches the next Monday, but not the one after it."""
        next_monday = AnnouncementFactory(
            session=self.session,
            needs_approval=True,
            approved_at=None,
            post_date=datetime.date(2026, 1, 26),
        )
        # Excluded: a week further out, so it waits for next Tuesday's email.
        AnnouncementFactory(
            session=self.session,
            needs_approval=True,
            approved_at=None,
            post_date=datetime.date(2026, 2, 2),
        )

        # Tuesday 2026-01-20, six days before Monday 2026-01-26.
        with freeze_time("2026-01-20 15:00:00"):
            schedule_approval_emails.call()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(next_monday.week_number), mail.outbox[0].subject)

    @rsps.activate
    def test_monday_post(self):
        """The daily job holds off until the announcement's Monday arrives."""
        rsps.add(rsps.POST, f"{BASE_URL}/channels/chan-1/messages", json={"id": "1"})
        announcement = AnnouncementFactory(
            session=self.session,
            needs_approval=True,
            approved_at=timezone.now(),
            post_date=datetime.date(2026, 1, 26),
        )

        # The Sunday before: nothing is due yet.
        with freeze_time("2026-01-25 15:00:00"):
            schedule_pending_announcements.call()
        self.assertEqual(len(rsps.calls), 0)

        with freeze_time("2026-01-26 15:00:00"):
            schedule_pending_announcements.call()

        self.assertEqual(len(rsps.calls), 1)
        announcement.refresh_from_db()
        self.assertIsNotNone(announcement.posted_at)
