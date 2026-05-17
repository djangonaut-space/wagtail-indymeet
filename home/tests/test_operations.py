"""
Tests for the Event sync trigger: operations.dispatch_event_sync, the
EventAdmin.save_model wiring that surfaces its result, and the model-level
field validators that replaced the old admin-form/service truncation.
"""

from datetime import datetime as dt
from datetime import timezone as dt_timezone
from unittest.mock import patch

from django.contrib import messages
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings

from accounts.factories import UserFactory
from home.admin import EventAdmin
from home.factories import EventFactory
from home.models import Event
from home.operations import EventSyncDecision, EventSyncStatus, dispatch_event_sync

ZOOM_SETTINGS = dict(
    ZOOM_ACCOUNT_ID="acct",
    ZOOM_CLIENT_ID="cid",
    ZOOM_CLIENT_SECRET="secret",
)
ZOOM_DISABLED = dict(ZOOM_ACCOUNT_ID="", ZOOM_CLIENT_ID="", ZOOM_CLIENT_SECRET="")

UTC = dt_timezone.utc


class DispatchEventSyncTests(TestCase):
    @override_settings(**ZOOM_SETTINGS)
    @patch("home.operations.sync_event")
    def test_queues_when_zoom_enabled(self, mock_task):
        event = EventFactory.create(zoom_link="")

        decision = dispatch_event_sync(event)

        self.assertEqual(decision.status, EventSyncStatus.QUEUED)
        mock_task.enqueue.assert_called_once_with(event_id=event.pk)

    @override_settings(**ZOOM_DISABLED)
    @patch("home.operations.sync_event")
    def test_queues_when_event_has_zoom_link_even_if_zoom_disabled(self, mock_task):
        event = EventFactory.create(zoom_link="https://zoom.us/j/manual")

        decision = dispatch_event_sync(event)

        self.assertEqual(decision.status, EventSyncStatus.QUEUED)
        mock_task.enqueue.assert_called_once_with(event_id=event.pk)

    @override_settings(**ZOOM_DISABLED)
    @patch("home.operations.sync_event")
    def test_queues_when_event_already_linked_to_discord(self, mock_task):
        event = EventFactory.create(zoom_link="", discord_event_id="d1")

        decision = dispatch_event_sync(event)

        self.assertEqual(decision.status, EventSyncStatus.QUEUED)
        mock_task.enqueue.assert_called_once_with(event_id=event.pk)

    @override_settings(**ZOOM_DISABLED)
    @patch("home.operations.sync_event")
    def test_dead_end_when_no_link_and_zoom_disabled(self, mock_task):
        event = EventFactory.create(zoom_link="")

        with self.assertLogs("home.operations", level="WARNING"):
            decision = dispatch_event_sync(event)

        self.assertEqual(decision.status, EventSyncStatus.SKIPPED_NO_ZOOM_CONFIGURED)
        mock_task.enqueue.assert_not_called()


class EventAdminSaveModelTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(
            email="savemodel@example.com", is_staff=True, is_superuser=True
        )

    def _request(self):
        request = self.factory.post("/admin/home/event/")
        request.user = self.superuser
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    @patch("home.admin.dispatch_event_sync")
    def test_queued_decision_shows_info_message(self, mock_dispatch):
        mock_dispatch.return_value = EventSyncDecision(
            EventSyncStatus.QUEUED, "Syncing now."
        )
        request = self._request()
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
        request = self._request()
        event = EventFactory.build(zoom_link="")

        self.admin.save_model(request, event, form=None, change=False)

        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].level, messages.WARNING)
        self.assertEqual(str(stored[0]), "No Zoom configured.")


class EventModelValidationTests(TestCase):
    """The Discord field-length caps now live as model validators (run on
    full_clean, i.e. every ModelForm) rather than in the admin form / service."""

    def _event(self, **kwargs):
        defaults = dict(
            title="Valid title",
            slug="valid-slug",
            start_time=dt(2026, 6, 1, 14, 0, tzinfo=UTC),
            end_time=dt(2026, 6, 1, 15, 0, tzinfo=UTC),
            zoom_link="https://zoom.us/j/123456789",
            extra_emails=["sessions@djangonaut.space"],
        )
        defaults.update(kwargs)
        return EventFactory.build(**defaults)

    def test_valid_event_passes_full_clean(self):
        self._event().full_clean()  # should not raise

    def test_zoom_link_over_discord_limit_fails(self):
        event = self._event(zoom_link="https://zoom.us/j/" + "z" * 100)
        with self.assertRaises(ValidationError) as ctx:
            event.full_clean()
        self.assertIn("zoom_link", ctx.exception.message_dict)

    def test_title_over_100_fails(self):
        event = self._event(title="x" * 101)
        with self.assertRaises(ValidationError) as ctx:
            event.full_clean()
        self.assertIn("title", ctx.exception.message_dict)

    def test_description_over_1000_fails(self):
        event = self._event(description="y" * 1001)
        with self.assertRaises(ValidationError) as ctx:
            event.full_clean()
        self.assertIn("description", ctx.exception.message_dict)
