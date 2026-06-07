"""Tests for the Event sync trigger: operations.dispatch_event_sync."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from home.factories import EventFactory
from home.operations import EventSyncStatus, dispatch_event_sync

ZOOM_SETTINGS = dict(
    ZOOM_ACCOUNT_ID="acct",
    ZOOM_CLIENT_ID="cid",
    ZOOM_CLIENT_SECRET="secret",
)
ZOOM_DISABLED = dict(ZOOM_ACCOUNT_ID="", ZOOM_CLIENT_ID="", ZOOM_CLIENT_SECRET="")


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
