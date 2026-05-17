"""
Tests for Zoom integration: ZoomClient, the zoom service (create/update meeting),
and the Zoom behaviour of the sync_event task.
"""

import datetime
from datetime import datetime as dt
from datetime import timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from home.factories import EventFactory
from home.integrations.zoom.client import TOKEN_CACHE_KEY, ZoomClient
from home.integrations.zoom.service import (
    ZoomMeeting,
    create_event_meeting,
    update_event_meeting,
    zoom_enabled,
)
from home.models import Event
from home.tasks.sync_event import sync_event

ZOOM_SETTINGS = dict(
    ZOOM_ACCOUNT_ID="acct",
    ZOOM_CLIENT_ID="cid",
    ZOOM_CLIENT_SECRET="secret",
)

UTC = dt_timezone.utc


class ZoomEnabledTests(TestCase):
    def test_returns_true_when_credentials_present(self):
        with override_settings(**ZOOM_SETTINGS):
            self.assertTrue(zoom_enabled())

    def test_returns_false_when_any_credential_missing(self):
        cases = [
            dict(ZOOM_ACCOUNT_ID="", ZOOM_CLIENT_ID="cid", ZOOM_CLIENT_SECRET="sec"),
            dict(ZOOM_ACCOUNT_ID="acct", ZOOM_CLIENT_ID="", ZOOM_CLIENT_SECRET="sec"),
            dict(ZOOM_ACCOUNT_ID="acct", ZOOM_CLIENT_ID="cid", ZOOM_CLIENT_SECRET=""),
        ]

        for cfg in cases:
            with override_settings(**cfg):
                self.assertFalse(zoom_enabled())


class ZoomClientGetAccessTokenTests(TestCase):
    def setUp(self):
        self.client = ZoomClient()

    @override_settings(**ZOOM_SETTINGS)
    def test_returns_cached_token(self):
        cache.set(TOKEN_CACHE_KEY, "cached-token", 3600)
        self.addCleanup(cache.delete, TOKEN_CACHE_KEY)

        with patch.object(self.client.session, "post") as mock_post:
            token = self.client._get_access_token()

        self.assertEqual(token, "cached-token")
        mock_post.assert_not_called()

    @override_settings(**ZOOM_SETTINGS)
    def test_fetches_and_caches_token(self):
        cache.delete(TOKEN_CACHE_KEY)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "new-token",
            "expires_in": 3600,
        }

        with patch.object(
            self.client.session, "post", return_value=mock_resp
        ) as mock_post:
            token = self.client._get_access_token()

        self.assertEqual(token, "new-token")
        self.assertEqual(cache.get(TOKEN_CACHE_KEY), "new-token")
        mock_post.assert_called_once()

    @override_settings(**ZOOM_SETTINGS)
    def test_uses_correct_grant_type_and_auth(self):
        cache.delete(TOKEN_CACHE_KEY)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "tok",
            "expires_in": 3600,
        }

        with patch.object(
            self.client.session, "post", return_value=mock_resp
        ) as mock_post:
            self.client._get_access_token()

        kwargs = mock_post.call_args.kwargs

        self.assertEqual(kwargs["data"]["grant_type"], "account_credentials")
        self.assertEqual(kwargs["data"]["account_id"], "acct")
        self.assertEqual(kwargs["auth"], ("cid", "secret"))


class ZoomClientCreateMeetingTests(TestCase):
    def setUp(self):
        self.client = ZoomClient()

    def _mock_request(self, meeting_id=123):
        resp = MagicMock()
        resp.json.return_value = {
            "id": meeting_id,
            "join_url": "https://zoom.us/j/123",
            "start_url": "https://zoom.us/s/123",
        }
        return patch.object(self.client, "_request", return_value=resp)

    def test_returns_expected_fields(self):
        start = dt(2024, 6, 1, 14, 0, tzinfo=UTC)

        with self._mock_request():
            meeting = self.client.create_meeting("Test Meeting", start, 60)

        self.assertEqual(meeting["id"], 123)
        self.assertIn("join_url", meeting)
        self.assertIn("start_url", meeting)

    def test_payload_fields(self):
        start = dt(2024, 6, 1, 14, 0, tzinfo=UTC)

        with self._mock_request() as mock_req:
            self.client.create_meeting("My Event", start, 90)

        payload = mock_req.call_args.kwargs["json"]

        self.assertEqual(payload["topic"], "My Event")
        self.assertEqual(payload["type"], 2)
        self.assertEqual(payload["duration"], 90)
        self.assertEqual(payload["timezone"], "UTC")
        self.assertEqual(payload["start_time"], "2024-06-01T14:00:00Z")

    def test_duration_bounds(self):
        start = dt(2024, 6, 1, 14, 0, tzinfo=UTC)

        with self._mock_request() as mock_req:
            self.client.create_meeting("Long Event", start, 9999)

        self.assertEqual(mock_req.call_args.kwargs["json"]["duration"], 1440)

        with self._mock_request() as mock_req:
            self.client.create_meeting("Short Event", start, 0)

        self.assertEqual(mock_req.call_args.kwargs["json"]["duration"], 1)

    def test_start_time_normalised_to_utc(self):
        ist = dt_timezone(datetime.timedelta(hours=5, minutes=30))
        start = dt(2024, 6, 1, 14, 0, tzinfo=ist)

        with self._mock_request() as mock_req:
            self.client.create_meeting("Event", start, 60)

        payload = mock_req.call_args.kwargs["json"]

        self.assertEqual(payload["start_time"], "2024-06-01T08:30:00Z")


class ZoomClientRequestRetryTests(TestCase):
    def setUp(self):
        self.client = ZoomClient()

    @override_settings(**ZOOM_SETTINGS)
    def test_invalid_token_triggers_refresh_and_retry(self):
        cache.set(TOKEN_CACHE_KEY, "old-token", 3600)

        resp_401 = MagicMock(status_code=401)
        resp_200 = MagicMock(status_code=200)
        resp_200.raise_for_status.return_value = None

        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "new-token",
            "expires_in": 3600,
        }

        with (
            patch.object(
                self.client.session, "request", side_effect=[resp_401, resp_200]
            ) as mock_req,
            patch.object(self.client.session, "post", return_value=token_resp),
        ):
            response = self.client._request("GET", "https://api.zoom.us/v2/test")

        self.assertEqual(response, resp_200)
        self.assertEqual(mock_req.call_count, 2)
        self.assertEqual(cache.get(TOKEN_CACHE_KEY), "new-token")


class ZoomClientPatchMeetingTests(TestCase):
    def setUp(self):
        self.client = ZoomClient()

    def test_payload_shape(self):
        start = dt(2026, 6, 1, 14, 0, tzinfo=UTC)

        with patch.object(self.client, "_request") as mock_req:
            self.client.patch_meeting(
                meeting_id="123",
                topic="Updated Topic",
                start_time=start,
                duration_minutes=45,
            )

        method, url = mock_req.call_args.args[:2]
        payload = mock_req.call_args.kwargs["json"]

        self.assertEqual(method, "PATCH")
        self.assertTrue(url.endswith("/meetings/123"))
        self.assertEqual(payload["topic"], "Updated Topic")
        self.assertEqual(payload["start_time"], "2026-06-01T14:00:00Z")
        self.assertEqual(payload["duration"], 45)
        self.assertEqual(payload["timezone"], "UTC")


class CreateEventMeetingServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = EventFactory.create(
            title="Django Office Hours",
            start_time=dt(2024, 7, 1, 17, 0, tzinfo=UTC),
            end_time=dt(2024, 7, 1, 18, 30, tzinfo=UTC),
            zoom_link="",
        )

    @patch("home.integrations.zoom.service.zoom_client.create_meeting")
    def test_returns_zoom_meeting(self, mock_create):
        mock_create.return_value = {
            "id": 1,
            "join_url": "https://zoom.us/j/abc",
            "start_url": "https://zoom.us/s/abc",
        }

        result = create_event_meeting(self.event)

        self.assertIsInstance(result, ZoomMeeting)
        self.assertEqual(result.join_url, "https://zoom.us/j/abc")
        self.assertEqual(result.meeting_id, "1")

        mock_create.assert_called_once_with(
            topic="Django Office Hours",
            start_time=self.event.start_time,
            duration_minutes=90,
        )

    @patch("home.integrations.zoom.service.zoom_client.create_meeting")
    def test_duration_minimum_one_minute(self, mock_create):
        event = EventFactory.create(
            start_time=dt(2024, 8, 1, 10, 0, tzinfo=UTC),
            end_time=dt(2024, 8, 1, 10, 0, tzinfo=UTC),
            zoom_link="",
        )

        mock_create.return_value = {
            "id": 2,
            "join_url": "https://zoom.us/j/xyz",
            "start_url": "https://zoom.us/s/xyz",
        }

        create_event_meeting(event)

        self.assertEqual(mock_create.call_args.kwargs["duration_minutes"], 1)


class UpdateEventMeetingServiceTests(TestCase):
    @patch("home.integrations.zoom.service.zoom_client.patch_meeting")
    def test_calls_patch_meeting_with_event_fields(self, mock_patch):
        event = EventFactory.create(
            title="Existing",
            start_time=dt(2026, 9, 1, 10, 0, tzinfo=UTC),
            end_time=dt(2026, 9, 1, 11, 0, tzinfo=UTC),
            zoom_link="https://zoom.us/j/existing",
            zoom_meeting_id="meeting-123",
        )

        update_event_meeting(event)

        mock_patch.assert_called_once_with(
            meeting_id="meeting-123",
            topic="Existing",
            start_time=event.start_time,
            duration_minutes=60,
        )


class SyncEventZoomTests(TestCase):
    """Zoom behaviour of the single sync_event task (create and update paths)."""

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.sync_event.create_event_meeting")
    def test_creates_meeting_and_sets_fields(self, mock_create):
        mock_create.return_value = ZoomMeeting("https://zoom.us/j/meeting", "12345")
        event = EventFactory.create(zoom_link="")

        sync_event.call(event_id=event.pk)

        event.refresh_from_db()
        self.assertEqual(event.zoom_link, "https://zoom.us/j/meeting")
        self.assertEqual(event.zoom_meeting_id, "12345")
        self.assertIsNotNone(event.zoom_synced_at)

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.sync_event.create_event_meeting")
    def test_skips_create_when_zoom_link_exists(self, mock_create):
        event = EventFactory.create(zoom_link="https://existing.link")

        sync_event.call(event_id=event.pk)

        mock_create.assert_not_called()

    @override_settings(ZOOM_ACCOUNT_ID="", ZOOM_CLIENT_ID="", ZOOM_CLIENT_SECRET="")
    @patch("home.tasks.sync_event.create_event_meeting")
    def test_skips_zoom_when_not_configured(self, mock_create):
        event = EventFactory.create(zoom_link="")

        sync_event.call(event_id=event.pk)

        mock_create.assert_not_called()

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.sync_event.create_event_meeting")
    def test_handles_missing_event(self, mock_create):
        sync_event.call(event_id=999999)

        mock_create.assert_not_called()

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.sync_event.create_event_meeting")
    def test_zoom_error_leaves_link_empty(self, mock_create):
        mock_create.side_effect = Exception("Zoom API error")
        event = EventFactory.create(zoom_link="")

        sync_event.call(event_id=event.pk)

        event.refresh_from_db()
        self.assertEqual(event.zoom_link, "")

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.sync_event.create_event_meeting")
    def test_concurrent_link_preserved(self, mock_create):
        mock_create.return_value = ZoomMeeting("https://zoom.us/j/new", "111")
        event = EventFactory.create(zoom_link="")

        # Simulate a concurrent write committed after the task was enqueued; the
        # task's select_for_update re-reads the row and must not overwrite it.
        Event.objects.filter(pk=event.pk).update(
            zoom_link="https://zoom.us/j/concurrent"
        )

        sync_event.call(event_id=event.pk)

        event.refresh_from_db()
        self.assertEqual(event.zoom_link, "https://zoom.us/j/concurrent")
        mock_create.assert_not_called()

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.sync_event.update_event_meeting")
    def test_updates_meeting_when_meeting_id_present(self, mock_update):
        event = EventFactory.create(
            zoom_link="https://zoom.us/j/existing",
            zoom_meeting_id="meeting-123",
        )

        sync_event.call(event_id=event.pk)

        mock_update.assert_called_once()
        event.refresh_from_db()
        self.assertIsNotNone(event.zoom_synced_at)

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.sync_event.update_event_meeting")
    def test_update_error_leaves_synced_at_unset(self, mock_update):
        mock_update.side_effect = Exception("Zoom down")
        event = EventFactory.create(
            zoom_link="https://zoom.us/j/existing",
            zoom_meeting_id="meeting-123",
        )

        sync_event.call(event_id=event.pk)

        event.refresh_from_db()
        self.assertIsNone(event.zoom_synced_at)

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.sync_event.create_event_meeting")
    def test_model_save_does_not_trigger_sync(self, mock_create):
        """No post_save signal: saving an Event must not run the sync itself,
        so the sync_event write-back can't loop back into another sync."""
        event = EventFactory.create(zoom_link="")
        event.title = "Changed"
        event.save()

        mock_create.assert_not_called()
