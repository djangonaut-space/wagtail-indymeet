"""Tests for EventAdmin actions and save_model sync dispatch."""

from datetime import datetime
from datetime import timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import messages
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404, HttpResponseRedirect
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from icalendar import Calendar

from accounts.factories import UserFactory
from home.admin import (
    CalendarInvitesSentFilter,
    EventAdmin,
    EventCalendarInviteAdmin,
    InviteSentFilter,
)
from home.factories import EventFactory, SessionFactory, SessionMembershipFactory
from home.models import Event, EventCalendarInvite
from home.operations import EventSyncDecision, EventSyncStatus
from home.preview_email import calendar_invite_email_action
from home.templatetags.email_tags import time_is_link

ZOOM_SETTINGS = dict(
    ZOOM_ACCOUNT_ID="acct",
    ZOOM_CLIENT_ID="cid",
    ZOOM_CLIENT_SECRET="secret",
)
ZOOM_DISABLED = dict(ZOOM_ACCOUNT_ID="", ZOOM_CLIENT_ID="", ZOOM_CLIENT_SECRET="")


def _get_sequence(ical_bytes: bytes) -> int:
    """Return the SEQUENCE of the first VEVENT in raw .ics bytes."""
    vevent = next(
        c for c in Calendar.from_ical(ical_bytes).walk() if c.name == "VEVENT"
    )
    return vevent["SEQUENCE"]


class EventAdminCopyActionTests(TestCase):
    """Tests for the copy_event admin action."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )
        self.event = EventFactory.create(
            title="Original Event",
            slug="original-event",
            start_time=datetime(2025, 6, 1, 18, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2025, 6, 1, 20, 0, tzinfo=dt_timezone.utc),
        )

    def _get_request(self):
        """Build a POST request with session and messages support."""
        request = self.factory.post("/admin/home/event/")
        request.user = self.superuser
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        messages = FallbackStorage(request)
        request._messages = messages
        return request

    def test_copy_event_redirects_to_add_form_with_copy_from(self):
        """Action redirects to the add form with copy_from pointing to the original."""
        request = self._get_request()
        queryset = Event.objects.filter(pk=self.event.pk)

        response = self.admin.copy_event(request, queryset)

        self.assertIsInstance(response, HttpResponseRedirect)
        expected_url = reverse("admin:home_event_add")
        self.assertIn(expected_url, response.url)
        self.assertIn(f"copy_from={self.event.pk}", response.url)

    def test_copy_event_error_when_multiple_selected(self):
        """Action shows an error and returns None when more than one event is selected."""
        EventFactory.create(
            title="Second Event",
            slug="second-event",
            start_time=datetime(2025, 7, 1, 18, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2025, 7, 1, 20, 0, tzinfo=dt_timezone.utc),
        )
        request = self._get_request()
        queryset = Event.objects.all()

        response = self.admin.copy_event(request, queryset)

        self.assertIsNone(response)
        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("exactly one", str(stored[0]))

    def test_copy_event_does_not_create_new_event(self):
        """Action must not persist any new event record — only a redirect."""
        request = self._get_request()
        queryset = Event.objects.filter(pk=self.event.pk)
        count_before = Event.objects.count()

        self.admin.copy_event(request, queryset)

        self.assertEqual(Event.objects.count(), count_before)

    def test_saving_copied_form_creates_new_event_and_leaves_original_unchanged(
        self,
    ):
        """Submitting the pre-populated add form saves a new event; original is unmodified."""
        self.client.force_login(self.superuser)
        count_before = Event.objects.count()

        response = self.client.post(
            reverse("admin:home_event_add"),
            {
                "title": "Copied Event",
                "slug": "copied-event",
                "start_time_0": "2025-07-01",
                "start_time_1": "18:00:00",
                "end_time_0": "2025-07-01",
                "end_time_1": "20:00:00",
                "audience": "community",
                "extra_emails": "sessions@djangonaut.space",
                # The change form carries the read-only calendar invite
                # inline, whose management form it validates.
                "calendar_invites-TOTAL_FORMS": "0",
                "calendar_invites-INITIAL_FORMS": "0",
                "_save": "Save",
            },
        )

        self.assertRedirects(
            response,
            reverse("admin:home_event_changelist"),
            fetch_redirect_response=False,
        )
        self.assertEqual(Event.objects.count(), count_before + 1)
        new_event = Event.objects.get(slug="copied-event")
        self.assertEqual(new_event.title, "Copied Event")

        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "Original Event")


class EventAdminGetChangeformInitialDataTests(TestCase):
    """Tests for get_changeform_initial_data pre-population via copy_from."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )
        self.event = EventFactory.create(
            title="Source Event",
            slug="source-event",
            start_time=datetime(2025, 6, 1, 18, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2025, 6, 1, 20, 0, tzinfo=dt_timezone.utc),
            description="A great event.",
            zoom_link="https://zoom.us/j/existing",
            video_link="https://youtube.example.com/watch?v=abc",
            audience=Event.Audience.COMMUNITY,
            extra_emails=["sessions@djangonaut.space"],
        )

    def _get_add_request(self, copy_from=None):
        params = f"?copy_from={copy_from}" if copy_from else ""
        request = self.factory.get(f"/admin/home/event/add/{params}")
        request.user = self.superuser
        return request

    def test_pre_populates_scalar_fields_from_source(self):
        """Scalar fields are pre-populated from the source event."""
        request = self._get_add_request(copy_from=self.event.pk)
        initial = self.admin.get_changeform_initial_data(request)

        self.assertEqual(initial["title"], "Source Event")
        self.assertEqual(initial["slug"], "source-event")
        self.assertEqual(initial["description"], "A great event.")
        self.assertEqual(initial["zoom_link"], "")
        self.assertEqual(initial["video_link"], "")
        self.assertFalse(initial["is_published"])
        self.assertEqual(initial["audience"], Event.Audience.COMMUNITY)
        self.assertEqual(initial["extra_emails"], ["sessions@djangonaut.space"])

    def test_no_copy_from_returns_normal_initial(self):
        """Without copy_from the method behaves like the default implementation."""
        request = self._get_add_request()
        initial = self.admin.get_changeform_initial_data(request)

        self.assertNotIn("title", initial)
        self.assertNotIn("speakers", initial)

    def test_invalid_copy_from_raises_404(self):
        """A non-existent copy_from pk raises Http404."""
        request = self._get_add_request(copy_from=999_999)
        with self.assertRaises(Http404):
            self.admin.get_changeform_initial_data(request)


class EventAdminSendCalendarInvitesTests(TestCase):
    """Tests for the send_calendar_invites admin action."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )

    def _get_request(self, apply=True):
        data = {"apply": "1"} if apply else {}
        request = self.factory.post("/admin/home/event/", data)
        request.user = self.superuser
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    def _make_event(self, **kwargs):
        return EventFactory.create(
            start_time=datetime(2025, 9, 1, 18, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2025, 9, 1, 20, 0, tzinfo=dt_timezone.utc),
            **kwargs,
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_shows_confirmation_page_without_apply(self, mock_send):
        """Without the apply flag, the action renders a confirmation page and
        queues nothing."""
        event = self._make_event(title="Unconfirmed Event")

        response = self.admin.send_calendar_invites(
            self._get_request(apply=False), Event.objects.filter(pk=event.pk)
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Unconfirmed Event", response.content)
        mock_send.assert_not_called()
        self.assertFalse(event.calendar_invites.exists())

    @patch("home.tasks.event_notifications.email.send")
    def test_session_event_sends_to_session_members(self, mock_send):
        """A session event sends calendar invites to all session members."""
        session = SessionFactory.create()
        member1 = UserFactory.create(email="member1@example.com")
        member2 = UserFactory.create(email="member2@example.com")
        SessionMembershipFactory.create(session=session, user=member1)
        SessionMembershipFactory.create(session=session, user=member2)
        event = self._make_event(session=session, audience=Event.Audience.SESSION)

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_send.assert_called_once()
        self.assertEqual(
            set(mock_send.call_args.kwargs["bcc_list"]),
            {"member1@example.com", "member2@example.com"},
        )
        self.assertEqual(event.calendar_invites.sent().count(), 2)

    @patch("home.tasks.event_notifications.email.send")
    def test_community_event_sends_to_accepted_members(self, mock_send):
        """A community event sends to everyone who is an accepted session member."""
        opted_in = UserFactory.create(email="opted@example.com")
        SessionMembershipFactory.create(user=opted_in)

        UserFactory.create(email="nope@example.com")

        event = self._make_event(audience=Event.Audience.COMMUNITY, session=None)

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["bcc_list"], ["opted@example.com"])

    @patch("home.tasks.event_notifications.email.send")
    def test_public_event_sends_no_email_without_extra_emails(self, mock_send):
        """A public event invites no members, so without extra_emails nobody is mailed."""
        opted_in = UserFactory.create(email="opted@example.com")
        SessionMembershipFactory.create(user=opted_in)
        event = self._make_event(audience=Event.Audience.PUBLIC, extra_emails=[])

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_send.assert_not_called()

    @patch("home.tasks.event_notifications.email.send")
    def test_multiple_events_each_processed_independently(self, mock_send):
        """Selecting multiple events sends one email per event."""
        opted_in = UserFactory.create(email="opted@example.com")
        SessionMembershipFactory.create(user=opted_in)

        event1 = self._make_event(
            slug="ev-1", audience=Event.Audience.COMMUNITY, session=None
        )
        event2 = self._make_event(
            slug="ev-2", audience=Event.Audience.COMMUNITY, session=None
        )

        self.admin.send_calendar_invites(
            self._get_request(),
            Event.objects.filter(pk__in=[event1.pk, event2.pk]),
        )

        self.assertEqual(mock_send.call_count, 2)

    @patch("home.tasks.event_notifications.email.send")
    def test_success_message_shows_queued_count(self, mock_send):
        """A success message is shown with the number of events processed."""
        event = self._make_event()
        request = self._get_request()

        self.admin.send_calendar_invites(request, Event.objects.filter(pk=event.pk))

        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("1", str(stored[0]))

    @patch("home.tasks.event_notifications.email.send")
    def test_already_invited_recipients_are_not_remailed(self, mock_send):
        """Re-running the action mails nobody when every recipient has an invite."""
        opted_in = UserFactory.create(email="opted@example.com")
        SessionMembershipFactory.create(user=opted_in)
        event = self._make_event(audience=Event.Audience.COMMUNITY, session=None)

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )
        mock_send.reset_mock()

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_send.assert_not_called()

    @patch("home.tasks.event_notifications.email.send")
    def test_confirmation_page_shows_pending_recipients(self, mock_send):
        """The confirmation page lists only the recipients who would be mailed."""
        invited = UserFactory.create(email="invited@example.com")
        SessionMembershipFactory.create(user=invited)
        event = self._make_event(audience=Event.Audience.COMMUNITY, session=None)
        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        latecomer = UserFactory.create(email="latecomer@example.com")
        SessionMembershipFactory.create(user=latecomer)
        response = self.admin.send_calendar_invites(
            self._get_request(apply=False), Event.objects.filter(pk=event.pk)
        )

        self.assertContains(response, "latecomer@example.com")
        self.assertNotContains(response, "invited@example.com")

    @patch("home.tasks.event_notifications.email.send")
    def test_event_without_zoom_link_still_sends(self, mock_send):
        opted_in = UserFactory.create(email="opted@example.com")
        SessionMembershipFactory.create(user=opted_in)
        event = self._make_event(
            audience=Event.Audience.COMMUNITY, session=None, zoom_link=""
        )

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_send.assert_called_once()

    def test_confirmation_page_warns_about_missing_zoom_link(self):
        event = self._make_event(zoom_link="", title="Zoomless Event")

        response = self.admin.send_calendar_invites(
            self._get_request(apply=False), Event.objects.filter(pk=event.pk)
        )

        self.assertContains(response, 'class="warning"')
        self.assertContains(response, "1 event has no Zoom link yet")
        self.assertContains(response, "<strong>Zoomless Event</strong>")
        self.assertContains(response, "Resync to Zoom and Discord")

    def test_confirmation_page_shows_audience(self):
        event = self._make_event(audience=Event.Audience.COMMUNITY)

        response = self.admin.send_calendar_invites(
            self._get_request(apply=False), Event.objects.filter(pk=event.pk)
        )

        self.assertContains(response, "<th>Audience</th>", html=True)
        self.assertContains(response, "<td>Community</td>", html=True)

    def test_confirmation_page_has_no_warning_when_zoom_links_set(self):
        event = self._make_event(zoom_link="https://zoom.us/j/123")

        response = self.admin.send_calendar_invites(
            self._get_request(apply=False), Event.objects.filter(pk=event.pk)
        )

        self.assertNotContains(response, "no Zoom link yet")


class EventAdminCalendarInviteEmailActionTests(TestCase):
    """Tests for the calendar_invite_email_action preview action."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com", is_staff=True, is_superuser=True
        )

    def _get_request(self):
        request = self.factory.post("/admin/home/event/")
        request.user = self.superuser
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    @patch("home.preview_email.email.send")
    def test_sends_preview_to_admin(self, mock_send):
        event = EventFactory.create()
        request = self._get_request()

        calendar_invite_email_action(
            self.admin, request, Event.objects.filter(pk=event.pk)
        )

        mock_send.assert_called_once()
        self.assertEqual(
            mock_send.call_args.kwargs["recipient_list"], [self.superuser.email]
        )
        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn(self.superuser.email, str(stored[0]))

    @patch("home.preview_email.email.send")
    def test_error_when_multiple_selected(self, mock_send):
        events = EventFactory.create_batch(2)
        request = self._get_request()

        calendar_invite_email_action(
            self.admin, request, Event.objects.filter(pk__in=[e.pk for e in events])
        )

        mock_send.assert_not_called()
        stored = list(request._messages)
        self.assertEqual(stored[0].level, messages.ERROR)


class EventAdminResyncEventActionTests(TestCase):
    """Tests for the resync_event admin action."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )

    def _get_request(self):
        request = self.factory.post("/admin/home/event/")
        request.user = self.superuser
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.operations.sync_event")
    def test_queues_already_synced_events(self, mock_task):
        """Action force-resyncs events even if Zoom/Discord are already set."""
        fully_synced = EventFactory.create(
            zoom_link="https://zoom.us/j/y", discord_event_id="d1"
        )

        self.admin.resync_event(
            self._get_request(), Event.objects.filter(pk=fully_synced.pk)
        )

        mock_task.enqueue.assert_called_once_with(event_id=fully_synced.pk)

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.operations.sync_event")
    def test_shows_success_message_when_queued(self, _mock_task):
        event = EventFactory.create(zoom_link="", discord_event_id="")
        request = self._get_request()

        self.admin.resync_event(request, Event.objects.filter(pk=event.pk))

        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("resync queued for 1 event(s)", str(stored[0]))

    @override_settings(**ZOOM_DISABLED)
    @patch("home.operations.sync_event")
    def test_shows_warning_when_zoom_not_configured(self, mock_task):
        event = EventFactory.create(zoom_link="", discord_event_id="")
        request = self._get_request()

        with self.assertLogs("home.operations", level="WARNING"):
            self.admin.resync_event(request, Event.objects.filter(pk=event.pk))

        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("Zoom isn't configured", str(stored[0]))
        mock_task.enqueue.assert_not_called()

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.operations.sync_event")
    def test_shows_warning_when_invites_already_sent(self, _mock_task):
        """Resyncing an event that already emailed invites warns that those
        recipients won't see the updated Zoom/Discord details."""
        event = EventFactory.create(
            zoom_link="https://zoom.us/j/y",
            discord_event_id="d1",
        )
        EventCalendarInvite.objects.create(
            event=event,
            email="guest@example.com",
            sent_at=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
        )
        request = self._get_request()

        self.admin.resync_event(request, Event.objects.filter(pk=event.pk))

        stored = [str(m) for m in request._messages]
        self.assertTrue(any("won't reflect the updated" in m for m in stored))


class EventAdminSaveModelTests(TestCase):
    """Tests for the save_model wiring that dispatches the Zoom/Discord sync
    and surfaces its result to the admin user."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(
            email="savemodel@example.com", is_staff=True, is_superuser=True
        )

    def _get_request(self):
        request = self.factory.post("/admin/home/event/")
        request.user = self.superuser
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    @patch("home.admin.dispatch_event_sync")
    def test_queued_decision_shows_info_message(self, mock_dispatch):
        mock_dispatch.return_value = EventSyncDecision(
            EventSyncStatus.QUEUED, "Syncing now."
        )
        request = self._get_request()
        event = EventFactory.build(zoom_link="https://zoom.us/j/x")

        self.admin.save_model(request, event, form=None, change=False)

        mock_dispatch.assert_called_once_with(event)
        stored = list(request._messages)
        self.assertEqual(stored[0].level, messages.INFO)
        self.assertEqual(str(stored[0]), "Syncing now.")

    @patch("home.admin.dispatch_event_sync")
    def test_dead_end_decision_shows_warning_message(self, mock_dispatch):
        mock_dispatch.return_value = EventSyncDecision(
            EventSyncStatus.SKIPPED_NO_ZOOM_CONFIGURED, "No Zoom configured."
        )
        request = self._get_request()
        event = EventFactory.build(zoom_link="")

        self.admin.save_model(request, event, form=None, change=False)

        stored = list(request._messages)
        self.assertEqual(stored[0].level, messages.WARNING)
        self.assertEqual(str(stored[0]), "No Zoom configured.")

    @patch("home.admin.dispatch_event_sync")
    def test_reminds_to_send_calendar_invites(self, mock_dispatch):
        """Saving always shows a reminder to use the calendar invites action."""
        mock_dispatch.return_value = EventSyncDecision(
            EventSyncStatus.QUEUED, "Syncing now."
        )
        request = self._get_request()
        event = EventFactory.build(zoom_link="https://zoom.us/j/x")

        self.admin.save_model(request, event, form=None, change=False)

        stored = [str(m) for m in request._messages]
        self.assertTrue(any("Send calendar invites" in m for m in stored))


@patch(
    "home.admin.dispatch_event_sync",
    return_value=EventSyncDecision(EventSyncStatus.QUEUED, "Syncing now."),
)
@patch("home.tasks.event_notifications.email.send")
class EventAdminTimeChangeTests(TestCase):
    """Updated invites are only emailed through the admin action."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.event = EventFactory.create(audience=Event.Audience.PUBLIC, session=None)
        EventCalendarInvite.objects.create(
            event=self.event, email="sent@example.com", sent_at=timezone.now()
        )
        EventCalendarInvite.objects.create(event=self.event, email="queued@example.com")

    def _get_request(self, apply: bool = False):
        request = self.factory.post(
            "/admin/home/event/", {"apply": "1"} if apply else {}
        )
        request.user = self.superuser
        SessionMiddleware(lambda req: None).process_request(request)
        request._messages = FallbackStorage(request)
        return request

    def _save(self, changed_data: list[str]) -> list[str]:
        request = self._get_request()
        form = SimpleNamespace(changed_data=changed_data)
        self.admin.save_model(request, self.event, form=form, change=True)
        return [str(m) for m in request._messages]

    def test_save_warns_without_sending(self, mock_send, _mock_dispatch):
        stored = self._save(["start_time"])

        mock_send.assert_not_called()
        self.event.refresh_from_db()
        self.assertEqual(self.event.calendar_sequence, 0)
        self.assertTrue(any("Send time(s) changed" in m for m in stored))

    def test_no_warning_for_other_changes(self, mock_send, _mock_dispatch):
        stored = self._save(["title"])

        self.assertFalse(any("Send time(s) changed" in m for m in stored))

    def test_no_warning_without_sent_invites(self, mock_send, _mock_dispatch):
        self.event.calendar_invites.sent().delete()

        stored = self._save(["end_time"])

        self.assertFalse(any("Send time(s) changed" in m for m in stored))

    def test_action_confirms_recipients(self, mock_send, _mock_dispatch):
        """Nothing is sent until the recipients are confirmed."""
        response = self.admin.send_calendar_updates(
            self._get_request(), Event.objects.filter(pk=self.event.pk)
        )

        mock_send.assert_not_called()
        content = " ".join(response.content.decode().split())
        self.assertIn("1 to be emailed: sent@example.com", content)
        self.assertNotIn("queued@example.com", content)
        self.assertIn('value="send_calendar_updates"', content)

    def test_action_emails_update(self, mock_send, _mock_dispatch):
        """Only people already sent an invite get the update."""
        request = self._get_request(apply=True)

        self.admin.send_calendar_updates(
            request, Event.objects.filter(pk=self.event.pk)
        )

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["email_template"], "event_calendar_update")
        self.assertEqual(kwargs["bcc_list"], ["sent@example.com"])
        self.assertEqual(_get_sequence(kwargs["attachments"][0][1]), 1)


class EventAdminSyncedDisplayTests(TestCase):
    """Tests for the zoom_synced/discord_synced list_display methods."""

    def setUp(self):
        self.admin = EventAdmin(Event, AdminSite())

    def test_reflects_synced_at_timestamps(self):
        """Each method is True only when its *_synced_at timestamp is set."""
        synced = EventFactory.build(
            zoom_synced_at=datetime.now(dt_timezone.utc), discord_synced_at=None
        )
        unsynced = EventFactory.build(zoom_synced_at=None, discord_synced_at=None)

        self.assertTrue(self.admin.zoom_synced(synced))
        self.assertFalse(self.admin.discord_synced(synced))
        self.assertFalse(self.admin.zoom_synced(unsynced))
        self.assertFalse(self.admin.discord_synced(unsynced))


class EventAdminStartTimeLinkTests(TestCase):
    """Tests for the start_time_link list_display method."""

    def test_links_to_time_is_comparison(self):
        """The start time renders in DATETIME_FORMAT, followed by a
        (time.is) link."""
        event = EventFactory.build(
            start_time=datetime(2025, 9, 1, 18, 0, tzinfo=dt_timezone.utc)
        )

        html = EventAdmin(Event, AdminSite()).start_time_link(event)

        self.assertIn(time_is_link(event.start_time), html)
        expected = date_format(
            timezone.template_localtime(event.start_time), "DATETIME_FORMAT"
        )
        self.assertIn(expected, html)
        self.assertIn("(time.is)", html)


class CalendarInvitesSentFilterTests(TestCase):
    """Tests for the CalendarInvitesSentFilter list filter."""

    def _filtered(self, value, queryset):
        request = RequestFactory().get(
            "/admin/home/event/", {"calendar_invites_sent": value}
        )
        filter_instance = CalendarInvitesSentFilter(
            request, request.GET.copy(), Event, EventAdmin
        )
        return set(filter_instance.queryset(request, queryset))

    def test_splits_events_by_sent_status(self):
        """none/any/all partition events by how many invites were emailed."""
        now = datetime.now(dt_timezone.utc)
        all_sent = EventFactory.create()
        EventCalendarInvite.objects.create(
            event=all_sent, email="guest@example.com", sent_at=now
        )
        partly_sent = EventFactory.create()
        EventCalendarInvite.objects.create(
            event=partly_sent, email="guest@example.com", sent_at=now
        )
        EventCalendarInvite.objects.create(
            event=partly_sent, email="queued@example.com"
        )
        unsent = EventFactory.create()
        EventCalendarInvite.objects.create(event=unsent, email="queued@example.com")
        no_invites = EventFactory.create()
        queryset = Event.objects.filter(
            pk__in=[all_sent.pk, partly_sent.pk, unsent.pk, no_invites.pk]
        )

        self.assertEqual(self._filtered("none", queryset), {unsent, no_invites})
        self.assertEqual(self._filtered("any", queryset), {all_sent, partly_sent})
        self.assertEqual(self._filtered("all", queryset), {all_sent})


class EventAdminReadonlyFieldsTests(TestCase):
    """Tests for EventAdmin's readonly_fields and fieldsets configuration."""

    def test_sync_id_fields_are_readonly(self):
        readonly = EventAdmin(Event, AdminSite()).readonly_fields
        self.assertIn("zoom_meeting_id", readonly)
        self.assertIn("discord_event_id", readonly)

    def test_calendar_invites_sent_is_readonly(self):
        """It's derived from the invite records, so there is nothing to edit."""
        readonly = EventAdmin(Event, AdminSite()).readonly_fields
        self.assertIn("calendar_invites_sent", readonly)

    def test_fieldsets_include_every_editable_field(self):
        """Every field the form would otherwise render must be grouped
        somewhere, or Django's admin checks fail."""
        admin_instance = EventAdmin(Event, AdminSite())
        request = RequestFactory().get("/admin/home/event/add/")
        fielded = {
            field for _, opts in admin_instance.fieldsets for field in opts["fields"]
        }

        form = admin_instance.get_form(request)
        self.assertTrue(set(form.base_fields).issubset(fielded))


class InviteSentFilterTests(TestCase):
    def test_filters_by_sent_status(self):
        event = EventFactory.create()
        sent = EventCalendarInvite.objects.create(
            event=event, email="sent@example.com", sent_at=timezone.now()
        )
        unsent = EventCalendarInvite.objects.create(
            event=event, email="queued@example.com"
        )
        queryset = EventCalendarInvite.objects.all()

        def filtered(value):
            request = RequestFactory().get("/", {"sent": value} if value else {})
            instance = InviteSentFilter(
                request, request.GET.copy(), EventCalendarInvite, None
            )
            return set(instance.queryset(request, queryset))

        self.assertEqual(filtered("yes"), {sent})
        self.assertEqual(filtered("no"), {unsent})
        self.assertEqual(filtered(None), {sent, unsent})


class EventCalendarInviteAdminResendTests(TestCase):
    """Tests for the resend_invites action."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.event = EventFactory.create()
        cls.other_event = EventFactory.create()

    def setUp(self):
        self.admin = EventCalendarInviteAdmin(EventCalendarInvite, AdminSite())

    def _get_request(self):
        request = RequestFactory().post("/admin/home/eventcalendarinvite/")
        request.user = self.superuser
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    def test_changelist_documents_action(self):
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("admin:home_eventcalendarinvite_changelist"))

        self.assertContains(response, "Help: actions &amp; columns on this page")
        self.assertContains(response, "<strong>Resend selected invites</strong>")

    def _invite(self, event: Event, address: str) -> EventCalendarInvite:
        return EventCalendarInvite.objects.create(
            event=event, email=address, sent_at=timezone.now()
        )

    @patch("home.tasks.event_notifications.email.send")
    def test_resends_only_selected(self, mock_send):
        """Selected invites are emailed again; the rest of the event isn't."""
        selected = [self._invite(self.event, f"a{i}@example.com") for i in range(2)]
        untouched = self._invite(self.event, "skip@example.com")
        request = self._get_request()

        self.admin.resend_invites(
            request,
            EventCalendarInvite.objects.filter(pk__in=[i.pk for i in selected]),
        )

        mock_send.assert_called_once()
        self.assertEqual(
            set(mock_send.call_args.kwargs["bcc_list"]),
            {"a0@example.com", "a1@example.com"},
        )
        self.assertFalse(self.event.calendar_invites.unsent().exists())
        untouched_sent_at = untouched.sent_at
        untouched.refresh_from_db()
        self.assertEqual(untouched.sent_at, untouched_sent_at)
        self.assertIn("Resending 2", str(list(request._messages)[0]))

    @patch("home.tasks.event_notifications.email.send")
    def test_batches_per_event(self, mock_send):
        """Invites for different events never share an email."""
        self._invite(self.event, "one@example.com")
        self._invite(self.other_event, "two@example.com")

        self.admin.resend_invites(
            self._get_request(), EventCalendarInvite.objects.all()
        )

        self.assertEqual(
            sorted(
                (c.kwargs["context"]["event"].pk, tuple(c.kwargs["bcc_list"]))
                for c in mock_send.call_args_list
            ),
            sorted(
                [
                    (self.event.pk, ("one@example.com",)),
                    (self.other_event.pk, ("two@example.com",)),
                ]
            ),
        )
