"""Tests for announcement generation and the week-number plumbing."""

import datetime

from django.test import TestCase

from accounts.factories import UserFactory
from home import constants
from home.announcements import TEMPLATE_FIELDS, WEEKLY_ANNOUNCEMENTS
from home.factories import (
    SessionFactory,
    SessionMembershipFactory,
)
from home.integrations.discord.service import MESSAGE_CONTENT_MAX
from home.models import Announcement
from home.services.session_announcements import (
    build_template_context,
    generate_announcements,
)


class AnnouncementTemplateTestCase(TestCase):
    def test_week_numbers(self):
        """Week numbers are unique and ordered, so generation can key off them."""
        week_numbers = [template.week_number for template in WEEKLY_ANNOUNCEMENTS]

        self.assertEqual(week_numbers, sorted(set(week_numbers)))

    def test_message_length(self):
        """Every template must fit Discord's cap after the week header is added."""
        session = SessionFactory()
        context = build_template_context(session)
        for template in WEEKLY_ANNOUNCEMENTS:
            with self.subTest(week_number=template.week_number):
                announcement = Announcement(
                    session=session,
                    week_number=template.week_number,
                    message=template.render(context),
                )
                self.assertLessEqual(
                    len(announcement.discord_content), MESSAGE_CONTENT_MAX
                )

    def test_template_fields(self):
        """Templates may only interpolate fields build_template_context supplies."""
        context = dict.fromkeys(TEMPLATE_FIELDS, "x")
        for template in WEEKLY_ANNOUNCEMENTS:
            with self.subTest(week_number=template.week_number):
                template.render(context)

    def test_approval_notes(self):
        """A template needs a note when, and only when, it needs approval."""
        for template in WEEKLY_ANNOUNCEMENTS:
            with self.subTest(week_number=template.week_number):
                self.assertEqual(bool(template.approval_note), template.needs_approval)

    def test_placeholders_need_approval(self):
        """Copy an organizer still has to fill in must never post on its own."""
        context = dict.fromkeys(TEMPLATE_FIELDS, "x")
        for template in WEEKLY_ANNOUNCEMENTS:
            if "<" in template.render(context):
                with self.subTest(week_number=template.week_number):
                    self.assertTrue(template.needs_approval)

    def test_automatic_templates_use_no_session_fields(self):
        """A missing session field must not silently degrade an auto-post.

        Templates that post without review are rendered against an empty
        context, so any ``{field}`` in them fails here rather than in Discord.
        """
        for template in WEEKLY_ANNOUNCEMENTS:
            if not template.needs_approval:
                with self.subTest(week_number=template.week_number):
                    template.render({})


class GenerateAnnouncementsTestCase(TestCase):
    def setUp(self):
        self.session = SessionFactory(
            start_date=datetime.date(2026, 1, 14),
            end_date=datetime.date(2026, 3, 18),
        )

    def test_creates_one_per_template(self):
        created = generate_announcements(self.session)

        self.assertEqual(created, len(WEEKLY_ANNOUNCEMENTS))
        self.assertEqual(
            list(self.session.announcements.values_list("week_number", flat=True)),
            [template.week_number for template in WEEKLY_ANNOUNCEMENTS],
        )

    def test_post_dates(self):
        """Every generated announcement lands on a Monday, whatever the start day."""
        generate_announcements(self.session)

        for announcement in self.session.announcements.all():
            with self.subTest(week_number=announcement.week_number):
                self.assertEqual(announcement.post_date.weekday(), 0)

    def test_week_zero_post_date(self):
        """Week 0 is the welcome message, so it goes out before the session starts."""
        generate_announcements(self.session)
        week_zero = self.session.announcements.get(week_number=0)

        self.assertEqual(week_zero.post_date, datetime.date(2026, 1, 5))
        self.assertLess(week_zero.post_date, self.session.start_date)

    def test_needs_approval(self):
        """Weeks whose copy is complete post on their own; the rest are gated."""
        generate_announcements(self.session)

        self.assertEqual(
            {
                announcement.week_number: announcement.needs_approval
                for announcement in self.session.announcements.all()
            },
            {
                template.week_number: template.needs_approval
                for template in WEEKLY_ANNOUNCEMENTS
            },
        )

    def test_fills_in_session_fields(self):
        """Week 0 names the organizers and links the session's feedback form."""
        self.session.feedback_form_url = "https://forms.example.com/feedback"
        self.session.save()
        for name in ("Ada Lovelace", "Grace Hopper"):
            first_name, last_name = name.split()
            SessionMembershipFactory(
                session=self.session,
                user=UserFactory(first_name=first_name, last_name=last_name),
                role=constants.ORGANIZER,
            )

        generate_announcements(self.session)

        message = self.session.announcements.get(week_number=0).message
        self.assertIn("Ada Lovelace and Grace Hopper", message)
        self.assertIn("https://forms.example.com/feedback", message)

    def test_missing_session_fields_stay_placeholders(self):
        """An unset field leaves a visible gap for the approver to catch."""
        generate_announcements(self.session)

        message = self.session.announcements.get(week_number=0).message
        self.assertIn("<session organizer names>", message)
        self.assertIn("<feedback form link>", message)

    def test_rerun_creates_nothing(self):
        generate_announcements(self.session)

        self.assertEqual(generate_announcements(self.session), 0)
        self.assertEqual(self.session.announcements.count(), len(WEEKLY_ANNOUNCEMENTS))

    def test_rerun_preserves_changes(self):
        """Rerunning Discord setup must not revert edits, approvals or posts."""
        generate_announcements(self.session)
        edited = self.session.announcements.get(week_number=3)
        edited.message = "Organizer rewrote this"
        edited.approved_at = datetime.datetime(2026, 1, 20, tzinfo=datetime.UTC)
        edited.posted_at = datetime.datetime(2026, 1, 26, tzinfo=datetime.UTC)
        edited.save()

        generate_announcements(self.session)

        edited.refresh_from_db()
        self.assertEqual(edited.message, "Organizer rewrote this")
        self.assertIsNotNone(edited.approved_at)
        self.assertIsNotNone(edited.posted_at)

    def test_rerun_after_delete(self):
        """A deleted week comes back on rerun.

        Generation keys off the weeks that exist, so this is the one case
        where a rerun adds something: it treats the missing week as one the
        session never had.
        """
        generate_announcements(self.session)
        self.session.announcements.filter(week_number=5).delete()

        self.assertEqual(generate_announcements(self.session), 1)
        self.assertEqual(self.session.announcements.count(), len(WEEKLY_ANNOUNCEMENTS))

    def test_scoped_to_one_session(self):
        other_session = SessionFactory(
            start_date=datetime.date(2026, 1, 14),
            end_date=datetime.date(2026, 3, 18),
        )

        generate_announcements(self.session)

        self.assertEqual(other_session.announcements.count(), 0)
