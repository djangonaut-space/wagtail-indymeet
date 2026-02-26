"""
Tests for iCalendar generation and the send_event_calendar_invite task.
"""

from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase
from icalendar import Calendar

from home.factories import EventFactory
from home.icalendar_utils import generate_icalendar
from home.tasks.event_notifications import send_event_calendar_invite


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
            location="https://zoom.us/j/123456",
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
        self.assertEqual(str(vevent["LOCATION"]), "https://zoom.us/j/123456")
        self.assertIn(self.event.slug, str(vevent["URL"]))
        self.assertEqual(str(vevent["DESCRIPTION"]), "A fun Django meetup.")

    def test_description_omitted_when_blank(self):
        event = EventFactory.create(
            start_time=datetime(2024, 4, 1, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2024, 4, 1, 11, 0, tzinfo=dt_timezone.utc),
            description="",
        )
        vevent = _get_vevent(generate_icalendar(event))
        self.assertNotIn("DESCRIPTION", vevent)


class SendEventCalendarInviteTaskTests(TestCase):
    """Tests for the send_event_calendar_invite task."""

    @classmethod
    def setUpTestData(cls):
        cls.event = EventFactory.create(
            title="Sprint Planning",
            start_time=datetime(2024, 5, 10, 15, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2024, 5, 10, 16, 0, tzinfo=dt_timezone.utc),
            extra_emails=["sessions@djangonaut.space"],
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_sends_calendar_invite_email(self, mock_send):
        """Task sends one email with correct template, recipients, context, and .ics attachment."""
        send_event_calendar_invite.call(
            event_id=self.event.pk,
            recipients=["participant@example.com"],
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]

        self.assertEqual(call_kwargs["email_template"], "event_calendar_invite")
        self.assertIn("participant@example.com", call_kwargs["recipient_list"])
        self.assertIn("sessions@djangonaut.space", call_kwargs["recipient_list"])
        self.assertEqual(call_kwargs["context"]["event"], self.event)
        self.assertIn("cta_link", call_kwargs["context"])

        filename, content, mimetype = call_kwargs["attachments"][0]
        self.assertEqual(filename, "event.ics")
        self.assertEqual(mimetype, "text/calendar")
        self.assertEqual(str(_get_vevent(content)["SUMMARY"]), "Sprint Planning")

    @patch("home.tasks.event_notifications.email.send")
    def test_does_nothing_for_nonexistent_event(self, mock_send):
        """Task exits silently when the event ID does not exist."""
        send_event_calendar_invite.call(
            event_id=999_999,
            recipients=["participant@example.com"],
        )

        mock_send.assert_not_called()

    @patch("home.tasks.event_notifications.email.send")
    def test_only_primary_recipient_when_extra_emails_empty(self, mock_send):
        """When extra_emails is empty, only the primary recipient is in the list."""
        event = EventFactory.create(
            start_time=datetime(2024, 6, 1, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2024, 6, 1, 11, 0, tzinfo=dt_timezone.utc),
            extra_emails=[],
        )

        send_event_calendar_invite.call(
            event_id=event.pk,
            recipients=["solo@example.com"],
        )

        self.assertEqual(mock_send.call_args[1]["recipient_list"], ["solo@example.com"])
