"""
Tests for iCalendar generation and the send_event_calendar_invite task.
"""

from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from icalendar import Calendar

from accounts.factories import UserFactory
from home.factories import EventFactory, SessionFactory, SessionMembershipFactory
from home.icalendar_utils import generate_icalendar
from home.models import Event, EventCalendarInvite
from home.tasks.event_notifications import (
    send_calendar_invite_email,
    send_event_calendar_invite,
)


def _get_vevent(ical_bytes: bytes):
    """Parse raw .ics bytes and return the first VEVENT component."""
    cal = Calendar.from_ical(ical_bytes)
    for component in cal.walk():
        if component.name == "VEVENT":
            return component
    raise AssertionError("No VEVENT found in calendar data")


class GenerateICalendarTests(TestCase):
    """Unit tests for generate_icalendar()."""

    @classmethod
    def setUpTestData(cls):
        cls.event = EventFactory.create(
            title="Django Meetup",
            start_time=datetime(2024, 3, 15, 18, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2024, 3, 15, 20, 0, tzinfo=dt_timezone.utc),
            description="A fun Django meetup.",
        )

    def test_calendar_metadata(self):
        """Output is bytes with correct PRODID, VERSION, and METHOD."""
        ical = generate_icalendar(self.event)
        self.assertIsInstance(ical, bytes)
        cal = Calendar.from_ical(ical)
        self.assertEqual(str(cal["PRODID"]), "-//Djangonaut Space//djangonaut.space//")
        self.assertEqual(str(cal["VERSION"]), "2.0")
        self.assertEqual(str(cal["METHOD"]), "PUBLISH")

    def test_vevent_fields(self):
        """VEVENT contains all expected fields from the event."""
        vevent = _get_vevent(generate_icalendar(self.event))
        self.assertEqual(str(vevent["UID"]), f"event-{self.event.pk}@djangonaut.space")
        self.assertEqual(str(vevent["SUMMARY"]), "Django Meetup")
        self.assertEqual(
            vevent.decoded("DTSTART"),
            datetime(2024, 3, 15, 18, 0, tzinfo=dt_timezone.utc),
        )
        self.assertEqual(
            vevent.decoded("DTEND"),
            datetime(2024, 3, 15, 20, 0, tzinfo=dt_timezone.utc),
        )
        self.assertEqual(str(vevent["URL"]), self.event.get_full_url())
        self.assertEqual(
            str(vevent["DESCRIPTION"]),
            f"A fun Django meetup.\n\nEvent details: {self.event.get_full_url()}",
        )
        self.assertNotIn("LOCATION", vevent)

    def test_description_without_event_description(self):
        event = EventFactory.create(
            start_time=datetime(2024, 4, 1, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2024, 4, 1, 11, 0, tzinfo=dt_timezone.utc),
            description="",
        )
        vevent = _get_vevent(generate_icalendar(event))
        self.assertEqual(
            str(vevent["DESCRIPTION"]), f"Event details: {event.get_full_url()}"
        )

    def test_unpublished_event_omits_event_page(self):
        event = EventFactory.create(is_published=False, description="")
        vevent = _get_vevent(generate_icalendar(event))
        self.assertNotIn("URL", vevent)
        self.assertNotIn("DESCRIPTION", vevent)

    def test_unpublished_event_with_zoom_link(self):
        event = EventFactory.create(
            is_published=False,
            zoom_link="https://zoom.us/j/123",
            description="Bring questions.",
        )
        vevent = _get_vevent(generate_icalendar(event))
        self.assertEqual(str(vevent["URL"]), "https://zoom.us/j/123")
        self.assertEqual(
            str(vevent["DESCRIPTION"]),
            "Join Zoom meeting: https://zoom.us/j/123\n\nBring questions.",
        )

    def test_zoom_link_is_primary_link(self):
        """The Zoom link, not Discord or the event page, is what people click."""
        event = EventFactory.create(
            zoom_link="https://zoom.us/j/123",
            description="See the event on Discord: https://discord.com/events/1/2",
        )
        vevent = _get_vevent(generate_icalendar(event))
        self.assertEqual(str(vevent["LOCATION"]), "https://zoom.us/j/123")
        self.assertEqual(str(vevent["URL"]), "https://zoom.us/j/123")
        self.assertEqual(
            str(vevent["DESCRIPTION"]),
            "Join Zoom meeting: https://zoom.us/j/123\n\n"
            "See the event on Discord: https://discord.com/events/1/2\n\n"
            f"Event details: {event.get_full_url()}",
        )


class SendEventCalendarInviteTaskTests(TestCase):
    """Tests for the send_event_calendar_invite task."""

    def setUp(self):
        self.session = SessionFactory.create()
        self.member = UserFactory.create(
            email="participant@example.com", first_name="Robin"
        )
        SessionMembershipFactory.create(session=self.session, user=self.member)
        self.event = EventFactory.create(
            title="Sprint Planning",
            start_time=datetime(2024, 5, 10, 15, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2024, 5, 10, 16, 0, tzinfo=dt_timezone.utc),
            session=self.session,
            extra_emails=["contact@djangonaut.space"],
        )

    def _sent_to(self, mock_send) -> set[str]:
        return {
            address
            for call in mock_send.call_args_list
            for address in call[1]["recipient_list"]
        }

    @patch("home.tasks.event_notifications.email.send")
    def test_sends_one_email_per_recipient(self, mock_send):
        """Each recipient is the sole addressee of their own email."""
        send_event_calendar_invite.call(event_id=self.event.pk)

        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(
            self._sent_to(mock_send),
            {"participant@example.com", "contact@djangonaut.space"},
        )
        for call in mock_send.call_args_list:
            self.assertEqual(len(call[1]["recipient_list"]), 1)
            self.assertIsNone(call[1].get("bcc_list"))

    @patch("home.tasks.event_notifications.email.send")
    def test_email_content(self, mock_send):
        """Each email uses the invite template, names the recipient, and attaches the .ics."""
        send_event_calendar_invite.call(event_id=self.event.pk)

        by_recipient = {
            call[1]["recipient_list"][0]: call[1] for call in mock_send.call_args_list
        }
        member_call = by_recipient["participant@example.com"]
        self.assertEqual(member_call["email_template"], "event_calendar_invite")
        self.assertEqual(member_call["from_email"], "sessions@djangonaut.space")
        self.assertEqual(member_call["context"]["event"], self.event)
        self.assertEqual(member_call["context"]["user"], self.member)
        self.assertEqual(member_call["context"]["name"], "Robin")
        self.assertIn("cta_link", member_call["context"])

        filename, content, mimetype = member_call["attachments"][0]
        self.assertEqual(filename, "event.ics")
        self.assertEqual(mimetype, "text/calendar")
        self.assertEqual(str(_get_vevent(content)["SUMMARY"]), "Sprint Planning")

        # extra_emails belong to guests with no account, so there's no name.
        guest_call = by_recipient["contact@djangonaut.space"]
        self.assertIsNone(guest_call["context"]["user"])
        self.assertEqual(guest_call["context"]["name"], "")

    @patch("home.tasks.event_notifications.email.send")
    def test_tracks_recipients(self, mock_send):
        """An invite is recorded per recipient, linked to the user where there is one."""
        send_event_calendar_invite.call(event_id=self.event.pk)

        invites = {invite.email: invite for invite in self.event.calendar_invites.all()}
        self.assertEqual(
            set(invites), {"participant@example.com", "contact@djangonaut.space"}
        )
        self.assertEqual(invites["participant@example.com"].user, self.member)
        self.assertIsNone(invites["contact@djangonaut.space"].user)
        for invite in invites.values():
            self.assertIsNotNone(invite.sent_at)
        self.assertEqual(
            list(self.event.calendar_invite_recipients.all()), [self.member]
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_rerun_only_mails_new_recipients(self, mock_send):
        """A second run skips recipients already invited and picks up new members."""
        send_event_calendar_invite.call(event_id=self.event.pk)
        mock_send.reset_mock()

        latecomer = UserFactory.create(email="latecomer@example.com")
        SessionMembershipFactory.create(session=self.session, user=latecomer)
        send_event_calendar_invite.call(event_id=self.event.pk)

        mock_send.assert_called_once()
        self.assertEqual(self._sent_to(mock_send), {"latecomer@example.com"})
        self.assertEqual(self.event.calendar_invites.count(), 3)

    @patch("home.tasks.event_notifications.email.send")
    def test_queued_invite_is_rescheduled(self, mock_send):
        """An invite queued but never sent is sent, without a second invite."""
        EventCalendarInvite.objects.create(
            event=self.event, email="participant@example.com"
        )

        send_event_calendar_invite.call(event_id=self.event.pk)

        self.assertEqual(self.event.calendar_invites.count(), 2)
        self.assertEqual(
            self._sent_to(mock_send),
            {"participant@example.com", "contact@djangonaut.space"},
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_queued_invite_matches_recipient_in_any_case(self, mock_send):
        """Invites are unique per address regardless of case."""
        EventCalendarInvite.objects.create(
            event=self.event, email="Participant@Example.com"
        )

        send_event_calendar_invite.call(event_id=self.event.pk)

        self.assertEqual(self.event.calendar_invites.count(), 2)
        self.assertEqual(
            self._sent_to(mock_send),
            {"Participant@Example.com", "contact@djangonaut.space"},
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_annotated_send_time_follows_the_invites(self, mock_send):
        """The event's send time is the most recent delivery to any recipient."""
        annotated = Event.objects.with_calendar_invites_sent_at()
        self.assertIsNone(annotated.get(pk=self.event.pk).calendar_invites_sent_at)

        send_event_calendar_invite.call(event_id=self.event.pk)

        self.assertEqual(
            annotated.get(pk=self.event.pk).calendar_invites_sent_at,
            self.event.calendar_invites.sent().latest("sent_at").sent_at,
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_does_nothing_for_nonexistent_event(self, mock_send):
        """Task exits silently when the event ID does not exist."""
        send_event_calendar_invite.call(event_id=999_999)
        mock_send.assert_not_called()

    @patch("home.tasks.event_notifications.email.send")
    def test_does_nothing_if_no_recipients(self, mock_send):
        """Task exits silently if no recipients are found."""
        event = EventFactory.create(is_public=False, session=None, extra_emails=[])
        send_event_calendar_invite.call(event_id=event.pk)
        mock_send.assert_not_called()
        self.assertFalse(event.calendar_invites.exists())

    def test_private_event_with_no_extra_emails_has_no_recipients(self):
        """A private event with no extra_emails has no recipients."""
        event = EventFactory.create(is_public=False, session=None, extra_emails=[])
        self.assertEqual(event.get_calendar_invite_recipients(), [])

    @patch("home.tasks.event_notifications.email.send")
    def test_private_event_sends_to_extra_emails(self, mock_send):
        """The invite task sends to extra_emails even for private, session-less events."""
        event = EventFactory.create(
            is_public=False,
            session=None,
            extra_emails=["sessions@djangonaut.space"],
        )
        send_event_calendar_invite.call(event_id=event.pk)
        mock_send.assert_called_once()
        self.assertEqual(
            mock_send.call_args[1]["recipient_list"], ["sessions@djangonaut.space"]
        )


class SendCalendarInviteEmailTaskTests(TestCase):
    """Tests for the per-recipient send_calendar_invite_email task."""

    def setUp(self):
        self.event = EventFactory.create(is_public=False, session=None)
        self.invite = EventCalendarInvite.objects.create(
            event=self.event, email="guest@example.com"
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_marks_invite_sent(self, mock_send):
        send_calendar_invite_email.call(invite_id=self.invite.pk)

        mock_send.assert_called_once()
        self.invite.refresh_from_db()
        self.assertIsNotNone(self.invite.sent_at)

    @patch("home.tasks.event_notifications.email.send")
    def test_skips_already_sent_invite(self, mock_send):
        """A recipient is never mailed twice, so a repeated run is harmless."""
        self.invite.sent_at = timezone.now()
        self.invite.save(update_fields=["sent_at"])

        send_calendar_invite_email.call(invite_id=self.invite.pk)

        mock_send.assert_not_called()

    @patch("home.tasks.event_notifications.email.send")
    def test_does_nothing_for_nonexistent_invite(self, mock_send):
        send_calendar_invite_email.call(invite_id=999_999)
        mock_send.assert_not_called()
