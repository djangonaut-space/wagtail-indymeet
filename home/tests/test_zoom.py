"""
Tests for Zoom meeting creation: ZoomClient, create_event_meeting service,
and the create_zoom_meeting task.
"""

import datetime
from datetime import datetime as dt, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from home.factories import EventFactory
from home.integrations.zoom.client import TOKEN_CACHE_KEY, ZoomClient
from home.integrations.zoom.service import create_event_meeting
from home.models import Event
from home.tasks.create_zoom_meeting import create_zoom_meeting, zoom_enabled

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

    def test_template_id_used_if_configured(self):
        start = dt(2024, 6, 1, 14, 0, tzinfo=UTC)

        with override_settings(ZOOM_MEETING_TEMPLATE_ID="tmpl-abc"):
            with self._mock_request() as mock_req:
                self.client.create_meeting("Event", start, 60)

        payload = mock_req.call_args.kwargs["json"]

        self.assertEqual(payload["template_id"], "tmpl-abc")
        self.assertNotIn("settings", payload)

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


class CreateEventMeetingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = EventFactory.create(
            title="Django Office Hours",
            start_time=dt(2024, 7, 1, 17, 0, tzinfo=UTC),
            end_time=dt(2024, 7, 1, 18, 30, tzinfo=UTC),
            video_link="",
        )

    @patch("home.integrations.zoom.service.zoom_client.create_meeting")
    def test_returns_join_url(self, mock_create):
        mock_create.return_value = {
            "id": 1,
            "join_url": "https://zoom.us/j/abc",
            "start_url": "https://zoom.us/s/abc",
        }

        url = create_event_meeting(self.event)

        self.assertEqual(url, "https://zoom.us/j/abc")

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
            video_link="",
        )

        mock_create.return_value = {
            "id": 2,
            "join_url": "https://zoom.us/j/xyz",
            "start_url": "https://zoom.us/s/xyz",
        }

        create_event_meeting(event)

        self.assertEqual(mock_create.call_args.kwargs["duration_minutes"], 1)


class CreateZoomMeetingTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = EventFactory.create(
            start_time=dt(2024, 9, 1, 10, 0, tzinfo=UTC),
            end_time=dt(2024, 9, 1, 11, 0, tzinfo=UTC),
            video_link="",
        )

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.create_zoom_meeting.create_event_meeting")
    def test_sets_video_link(self, mock_create):
        mock_create.return_value = "https://zoom.us/j/meeting"

        create_zoom_meeting.call(event_id=self.event.pk)

        self.event.refresh_from_db()
        self.assertEqual(self.event.video_link, "https://zoom.us/j/meeting")

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.create_zoom_meeting.create_event_meeting")
    def test_skips_if_video_link_exists(self, mock_create):
        event = EventFactory.create(video_link="https://existing.link")

        create_zoom_meeting.call(event_id=event.pk)

        mock_create.assert_not_called()

    @override_settings(ZOOM_ACCOUNT_ID="", ZOOM_CLIENT_ID="", ZOOM_CLIENT_SECRET="")
    @patch("home.tasks.create_zoom_meeting.create_event_meeting")
    def test_skips_when_zoom_not_configured(self, mock_create):
        create_zoom_meeting.call(event_id=self.event.pk)

        mock_create.assert_not_called()

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.create_zoom_meeting.create_event_meeting")
    def test_handles_missing_event(self, mock_create):
        create_zoom_meeting.call(event_id=999999)

        mock_create.assert_not_called()

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.create_zoom_meeting.create_event_meeting")
    def test_handles_zoom_errors(self, mock_create):
        mock_create.side_effect = Exception("Zoom API error")

        create_zoom_meeting.call(event_id=self.event.pk)

        self.event.refresh_from_db()
        self.assertEqual(self.event.video_link, "")

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.create_zoom_meeting.create_event_meeting")
    def test_concurrent_update_preserved(self, mock_create):
        mock_create.return_value = "https://zoom.us/j/new"

        event = EventFactory.create(video_link="")

        Event.objects.filter(pk=event.pk).update(
            video_link="https://zoom.us/j/concurrent"
        )

        create_zoom_meeting.call(event_id=event.pk)

        event.refresh_from_db()

        self.assertEqual(event.video_link, "https://zoom.us/j/concurrent")

    @override_settings(**ZOOM_SETTINGS)
    @patch("home.tasks.create_zoom_meeting.create_event_meeting")
    def test_uses_select_for_update_in_transaction(self, mock_create):
        """Task uses select_for_update inside an atomic transaction."""
        from django.db import transaction

        mock_create.return_value = "https://zoom.us/j/meeting"

        with (
            patch("django.db.transaction.atomic") as mock_atomic,
            patch(
                "home.tasks.create_zoom_meeting.Event.objects.select_for_update"
            ) as mock_select,
        ):

            # Setup the chain: Event.objects.select_for_update().get(pk=...)
            mock_select.return_value.get.return_value = self.event

            create_zoom_meeting.call(event_id=self.event.pk)

            self.assertTrue(mock_atomic.called)
            mock_select.assert_called_once()
            mock_select.return_value.get.assert_called_with(pk=self.event.pk)
