"""Tests for EventAdmin actions and save_model sync dispatch."""

from datetime import datetime
from datetime import timezone as dt_timezone
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

from accounts.factories import UserFactory
from home.admin import CalendarInvitesSentFilter, EventAdmin
from home.factories import EventFactory, SessionFactory, SessionMembershipFactory
from home.models import Event
from home.operations import EventSyncDecision, EventSyncStatus
from home.preview_email import calendar_invite_email_action
from home.templatetags.email_tags import time_is_link

ZOOM_SETTINGS = dict(
    ZOOM_ACCOUNT_ID="acct",
    ZOOM_CLIENT_ID="cid",
    ZOOM_CLIENT_SECRET="secret",
)
ZOOM_DISABLED = dict(ZOOM_ACCOUNT_ID="", ZOOM_CLIENT_ID="", ZOOM_CLIENT_SECRET="")


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
                "is_public": True,
                "extra_emails": "sessions@djangonaut.space",
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
            is_public=True,
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
        self.assertTrue(initial["is_public"])
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
        event = self._make_event(is_public=False, title="Unconfirmed Event")

        response = self.admin.send_calendar_invites(
            self._get_request(apply=False), Event.objects.filter(pk=event.pk)
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Unconfirmed Event", response.content)
        mock_send.assert_not_called()
        event.refresh_from_db()
        self.assertIsNone(event.calendar_invites_sent_at)

    @patch("home.tasks.event_notifications.email.send")
    def test_session_event_sends_to_session_members(self, mock_send):
        """A session event sends calendar invites to all session members."""
        session = SessionFactory.create()
        member1 = UserFactory.create(email="member1@example.com")
        member2 = UserFactory.create(email="member2@example.com")
        SessionMembershipFactory.create(session=session, user=member1)
        SessionMembershipFactory.create(session=session, user=member2)
        event = self._make_event(session=session, is_public=True)

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_send.assert_called_once()
        event.refresh_from_db()
        self.assertIsNotNone(event.calendar_invites_sent_at)

    @patch("home.tasks.event_notifications.email.send")
    def test_public_event_no_session_sends_to_opted_in_users(self, mock_send):
        """A public event with no session sends to users who are accepted session members."""
        opted_in = UserFactory.create(email="opted@example.com")
        SessionMembershipFactory.create(user=opted_in)

        UserFactory.create(email="nope@example.com")

        event = self._make_event(is_public=True, session=None)

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_send.assert_called_once()
        bcc = mock_send.call_args[1]["bcc_list"]
        self.assertIn("opted@example.com", bcc)
        self.assertNotIn("nope@example.com", bcc)

    @patch("home.tasks.event_notifications.email.send")
    def test_private_event_no_session_sends_no_email(self, mock_send):
        """A private event with no extra_emails sends no email because there are no recipients."""
        event = self._make_event(is_public=False, session=None, extra_emails=[])

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_send.assert_not_called()

    @patch("home.tasks.event_notifications.email.send")
    def test_multiple_events_each_processed_independently(self, mock_send):
        """Selecting multiple events sends one email per event."""
        opted_in = UserFactory.create(email="opted@example.com")
        SessionMembershipFactory.create(user=opted_in)

        event1 = self._make_event(slug="ev-1", is_public=True, session=None)
        event2 = self._make_event(slug="ev-2", is_public=True, session=None)

        self.admin.send_calendar_invites(
            self._get_request(),
            Event.objects.filter(pk__in=[event1.pk, event2.pk]),
        )

        self.assertEqual(mock_send.call_count, 2)

    @patch("home.tasks.event_notifications.email.send")
    def test_success_message_shows_queued_count(self, mock_send):
        """A success message is shown with the number of events processed."""
        event = self._make_event(is_public=False)
        request = self._get_request()

        self.admin.send_calendar_invites(request, Event.objects.filter(pk=event.pk))

        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("1", str(stored[0]))

    @patch("home.tasks.event_notifications.email.send")
    def test_skipped_message_shows_skipped_count(self, mock_send):
        """A warning message is shown with the number of events skipped."""
        event = self._make_event(
            is_public=False, calendar_invites_sent_at=datetime.now(dt_timezone.utc)
        )
        request = self._get_request()

        self.admin.send_calendar_invites(request, Event.objects.filter(pk=event.pk))

        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("Skipped 1 event(s)", str(stored[0]))
        mock_send.assert_not_called()

    @patch("home.tasks.event_notifications.email.send")
    def test_batch_with_sent_and_unsent_events_reports_both_outcomes(self, mock_send):
        """Selecting a mix of already-sent and pending events sends to the pending ones
        and skips the rest, showing separate success and warning messages."""
        opted_in = UserFactory.create(email="opted@example.com")
        SessionMembershipFactory.create(user=opted_in)

        already_sent = self._make_event(
            slug="ev-sent",
            is_public=True,
            session=None,
            calendar_invites_sent_at=datetime.now(dt_timezone.utc),
        )
        pending = self._make_event(slug="ev-pending", is_public=True, session=None)
        request = self._get_request()

        self.admin.send_calendar_invites(
            request,
            Event.objects.filter(pk__in=[already_sent.pk, pending.pk]),
        )

        mock_send.assert_called_once()
        message_texts = [str(m) for m in request._messages]
        self.assertEqual(len(message_texts), 2)
        self.assertTrue(any("queued for 1" in t for t in message_texts))
        self.assertTrue(any("Skipped 1" in t for t in message_texts))


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


class EventAdminRetryEventSyncActionTests(TestCase):
    """Tests for the retry_event_sync admin action."""

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
    def test_queues_events_that_are_not_fully_synced(self, mock_task):
        """Action enqueues events missing a Zoom link or Discord event and
        skips events that already have both."""
        missing_zoom = EventFactory.create(zoom_link="", discord_event_id="")
        missing_discord = EventFactory.create(
            zoom_link="https://zoom.us/j/x", discord_event_id=""
        )
        fully_synced = EventFactory.create(
            zoom_link="https://zoom.us/j/y", discord_event_id="d1"
        )
        queryset = Event.objects.filter(
            pk__in=[missing_zoom.pk, missing_discord.pk, fully_synced.pk]
        )

        self.admin.retry_event_sync(self._get_request(), queryset)

        enqueued_ids = {
            call.kwargs["event_id"] for call in mock_task.enqueue.call_args_list
        }
        self.assertEqual(enqueued_ids, {missing_zoom.pk, missing_discord.pk})

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.operations.sync_event")
    def test_shows_success_message_when_queued(self, _mock_task):
        event = EventFactory.create(zoom_link="", discord_event_id="")
        request = self._get_request()

        self.admin.retry_event_sync(request, Event.objects.filter(pk=event.pk))

        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("queued for 1 event(s)", str(stored[0]))

    @patch("home.operations.sync_event")
    def test_shows_info_message_for_already_synced_events(self, mock_task):
        event = EventFactory.create(
            zoom_link="https://zoom.us/j/x", discord_event_id="d1"
        )
        request = self._get_request()

        self.admin.retry_event_sync(request, Event.objects.filter(pk=event.pk))

        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("already synced", str(stored[0]))
        mock_task.enqueue.assert_not_called()

    @override_settings(**ZOOM_DISABLED)
    @patch("home.operations.sync_event")
    def test_shows_warning_when_zoom_not_configured(self, mock_task):
        event = EventFactory.create(zoom_link="", discord_event_id="")
        request = self._get_request()

        with self.assertLogs("home.operations", level="WARNING"):
            self.admin.retry_event_sync(request, Event.objects.filter(pk=event.pk))

        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("Zoom isn't configured", str(stored[0]))
        mock_task.enqueue.assert_not_called()


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
        self.assertEqual(len(stored), 1)
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
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].level, messages.WARNING)
        self.assertEqual(str(stored[0]), "No Zoom configured.")


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
        """The yes/no filter values partition events by invite-sent status."""
        sent = EventFactory.create(
            calendar_invites_sent_at=datetime.now(dt_timezone.utc)
        )
        unsent = EventFactory.create(calendar_invites_sent_at=None)
        queryset = Event.objects.filter(pk__in=[sent.pk, unsent.pk])

        self.assertEqual(self._filtered("yes", queryset), {sent})
        self.assertEqual(self._filtered("no", queryset), {unsent})

