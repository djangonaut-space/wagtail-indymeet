"""
Tests for iCalendar generation and the send_event_calendar_invite task.
"""

from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from icalendar import Calendar

from accounts.factories import UserFactory
from home.factories import EventFactory, SessionFactory, SessionMembershipFactory
from home.icalendar_utils import generate_icalendar
from home.models import Event, EventCalendarInvite
from home.tasks.event_notifications import (
    CALENDAR_INVITE_BATCH_SIZE,
    send_calendar_invite_batch,
    send_calendar_update_batch,
    send_event_calendar_invite,
    send_event_calendar_update,
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
        self.assertEqual(str(cal["METHOD"]), "REQUEST")

    def test_meeting_request_fields(self):
        """Calendars need an organizer, attendee and sequence to apply updates."""
        event = EventFactory.create(calendar_sequence=3)
        vevent = _get_vevent(generate_icalendar(event))
        self.assertEqual(vevent["SEQUENCE"], 3)
        self.assertEqual(str(vevent["ORGANIZER"]), "mailto:sessions@djangonaut.space")
        self.assertEqual(vevent["ORGANIZER"].params["CN"], "Djangonaut Space")
        self.assertEqual(str(vevent["ATTENDEE"]), "mailto:sessions@djangonaut.space")

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
            audience=Event.Audience.SESSION,
            session=self.session,
            extra_emails=["contact@djangonaut.space"],
        )

    def _sent_to(self, mock_send) -> set[str]:
        return {
            address
            for call in mock_send.call_args_list
            for address in call[1]["bcc_list"]
        }

    @patch("home.tasks.event_notifications.email.send")
    def test_bccs_recipients(self, mock_send):
        """Recipients share one email, BCC'd and addressed to the sessions inbox."""
        send_event_calendar_invite.call(event_id=self.event.pk)

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["recipient_list"], ["sessions@djangonaut.space"])
        self.assertEqual(
            set(kwargs["bcc_list"]),
            {"participant@example.com", "contact@djangonaut.space"},
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_batches(self, mock_send):
        """Large audiences are split into emails of at most the batch size."""
        for user in UserFactory.create_batch(CALENDAR_INVITE_BATCH_SIZE):
            SessionMembershipFactory.create(session=self.session, user=user)

        send_event_calendar_invite.call(event_id=self.event.pk)

        batch_sizes = [len(c.kwargs["bcc_list"]) for c in mock_send.call_args_list]
        self.assertEqual(batch_sizes, [CALENDAR_INVITE_BATCH_SIZE, 2])
        self.assertEqual(len(self._sent_to(mock_send)), CALENDAR_INVITE_BATCH_SIZE + 2)
        self.assertFalse(self.event.calendar_invites.unsent().exists())

    @patch("home.tasks.event_notifications.email.send")
    def test_email_content(self, mock_send):
        """The email uses the invite template and attaches the .ics."""
        send_event_calendar_invite.call(event_id=self.event.pk)

        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["email_template"], "event_calendar_invite")
        self.assertEqual(kwargs["from_email"], "sessions@djangonaut.space")
        self.assertEqual(kwargs["context"]["event"], self.event)
        self.assertIn("cta_link", kwargs["context"])

        filename, content, mimetype = kwargs["attachments"][0]
        self.assertEqual(filename, "event.ics")
        self.assertEqual(mimetype, "text/calendar")
        self.assertEqual(str(_get_vevent(content)["SUMMARY"]), "Sprint Planning")

    @override_settings(ENVIRONMENT="production")
    def test_rendered_greeting_is_generic(self):
        """A shared email can't greet each recipient by name."""
        send_event_calendar_invite.call(event_id=self.event.pk)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Hello,", mail.outbox[0].body)
        self.assertNotIn("Robin", mail.outbox[0].body)
        self.assertEqual(
            set(mail.outbox[0].bcc),
            {"participant@example.com", "contact@djangonaut.space"},
        )

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
        event = EventFactory.create(
            audience=Event.Audience.PUBLIC, session=None, extra_emails=[]
        )
        send_event_calendar_invite.call(event_id=event.pk)
        mock_send.assert_not_called()
        self.assertFalse(event.calendar_invites.exists())

    def test_public_event_with_no_extra_emails_has_no_recipients(self):
        """A public event with no extra_emails has no recipients."""
        event = EventFactory.create(
            audience=Event.Audience.PUBLIC, session=None, extra_emails=[]
        )
        self.assertEqual(event.get_calendar_invite_recipients(), [])

    @patch("home.tasks.event_notifications.email.send")
    def test_public_event_sends_to_extra_emails(self, mock_send):
        """The invite task sends to extra_emails for public events."""
        event = EventFactory.create(
            audience=Event.Audience.PUBLIC,
            session=None,
            extra_emails=["sessions@djangonaut.space"],
        )
        send_event_calendar_invite.call(event_id=event.pk)
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["recipient_list"], ["sessions@djangonaut.space"])
        # Already the To address, so it isn't BCC'd as well.
        self.assertEqual(kwargs["bcc_list"], [])
        self.assertIsNotNone(event.calendar_invites.get().sent_at)


class SendCalendarInviteBatchTaskTests(TestCase):
    """Tests for the send_calendar_invite_batch task."""

    def setUp(self):
        self.event = EventFactory.create(audience=Event.Audience.PUBLIC, session=None)
        self.invite = EventCalendarInvite.objects.create(
            event=self.event, email="guest@example.com"
        )
        self.other = EventCalendarInvite.objects.create(
            event=self.event, email="other@example.com"
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_marks_invites_sent(self, mock_send):
        send_calendar_invite_batch.call(invite_ids=[self.invite.pk, self.other.pk])

        mock_send.assert_called_once()
        self.assertFalse(self.event.calendar_invites.unsent().exists())

    @patch("home.tasks.event_notifications.email.send")
    def test_skips_already_sent_invite(self, mock_send):
        """A recipient is never mailed twice, so a repeated run is harmless."""
        self.invite.sent_at = timezone.now()
        self.invite.save(update_fields=["sent_at"])

        send_calendar_invite_batch.call(invite_ids=[self.invite.pk, self.other.pk])

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["bcc_list"], ["other@example.com"])

    @patch("home.tasks.event_notifications.email.send")
    def test_does_nothing_when_all_sent(self, mock_send):
        send_calendar_invite_batch.call(invite_ids=[999_999])
        mock_send.assert_not_called()

    @patch("home.tasks.event_notifications.email.send", side_effect=RuntimeError)
    def test_failed_send_leaves_batch_unsent(self, mock_send):
        """A failed send can be retried by sending the event's invites again."""
        with self.assertRaises(RuntimeError):
            send_calendar_invite_batch.call(invite_ids=[self.invite.pk, self.other.pk])

        self.assertEqual(self.event.calendar_invites.unsent().count(), 2)


class SendEventCalendarUpdateTaskTests(TestCase):
    """Tests for the send_event_calendar_update task."""

    def setUp(self):
        self.event = EventFactory.create(
            title="Sprint Planning",
            audience=Event.Audience.PUBLIC,
            session=None,
            calendar_sequence=1,
        )

    def _invite(self, address: str, sent: bool = True) -> EventCalendarInvite:
        return EventCalendarInvite.objects.create(
            event=self.event,
            email=address,
            sent_at=timezone.now() if sent else None,
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_sends_to_already_invited(self, mock_send):
        """People whose invite hasn't gone out yet will get the new time with it."""
        self._invite("sent@example.com")
        self._invite("queued@example.com", sent=False)

        send_event_calendar_update.call(event_id=self.event.pk)

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["email_template"], "event_calendar_update")
        self.assertEqual(kwargs["recipient_list"], ["sessions@djangonaut.space"])
        self.assertEqual(kwargs["bcc_list"], ["sent@example.com"])
        vevent = _get_vevent(kwargs["attachments"][0][1])
        self.assertEqual(str(vevent["UID"]), f"event-{self.event.pk}@djangonaut.space")

    @patch("home.tasks.event_notifications.email.send")
    def test_raises_sequence_each_time(self, mock_send):
        """Each update must outrank the last for calendars to apply it."""
        self._invite("sent@example.com")

        send_event_calendar_update.call(event_id=self.event.pk)
        send_event_calendar_update.call(event_id=self.event.pk)

        sequences = [
            _get_vevent(c.kwargs["attachments"][0][1])["SEQUENCE"]
            for c in mock_send.call_args_list
        ]
        self.assertEqual(sequences, [2, 3])

    @patch("home.tasks.event_notifications.email.send")
    def test_batches(self, mock_send):
        for i in range(CALENDAR_INVITE_BATCH_SIZE + 1):
            self._invite(f"person{i}@example.com")

        send_event_calendar_update.call(event_id=self.event.pk)

        batch_sizes = [len(c.kwargs["bcc_list"]) for c in mock_send.call_args_list]
        self.assertEqual(batch_sizes, [CALENDAR_INVITE_BATCH_SIZE, 1])

    @patch("home.tasks.event_notifications.email.send")
    def test_does_not_change_sent_at(self, mock_send):
        invite = self._invite("sent@example.com")

        send_event_calendar_update.call(event_id=self.event.pk)

        sent_at = invite.sent_at
        invite.refresh_from_db()
        self.assertEqual(invite.sent_at, sent_at)

    @patch("home.tasks.event_notifications.email.send")
    def test_batch_with_no_invites(self, mock_send):
        send_calendar_update_batch.call(invite_ids=[999_999])
        mock_send.assert_not_called()

    @override_settings(ENVIRONMENT="production")
    def test_rendered_email(self):
        self._invite("sent@example.com")

        send_event_calendar_update.call(event_id=self.event.pk)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Time changed: Sprint Planning")
        self.assertIn("The time for Sprint Planning has changed", mail.outbox[0].body)
