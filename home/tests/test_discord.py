"""
Tests for Discord integration: DiscordClient, the discord service
(create/update event, _prepare_fields), and the Discord behaviour of sync_event
(including the combined Zoom-then-Discord run in a single task).
"""

from datetime import datetime as dt
from datetime import timezone as dt_timezone
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, override_settings

from home.factories import EventFactory
from home.integrations.discord.client import DiscordClient
from home.integrations.discord.service import (
    _prepare_fields,
    discord_enabled,
    update_event,
)
from home.integrations.zoom.service import ZoomMeeting
from home.tasks.sync_event import sync_event

DISCORD_SETTINGS = dict(
    DISCORD_BOT_TOKEN="bot-token",
    DISCORD_GUILD_ID="123456789",
)

ZOOM_SETTINGS = dict(
    ZOOM_ACCOUNT_ID="acct",
    ZOOM_CLIENT_ID="cid",
    ZOOM_CLIENT_SECRET="secret",
)

UTC = dt_timezone.utc


class DiscordEnabledTests(TestCase):
    def test_returns_true_when_credentials_present(self):
        with override_settings(**DISCORD_SETTINGS):
            self.assertTrue(discord_enabled())

    def test_returns_false_when_any_credential_missing(self):
        cases = [
            dict(DISCORD_BOT_TOKEN="", DISCORD_GUILD_ID="123"),
            dict(DISCORD_BOT_TOKEN="tok", DISCORD_GUILD_ID=""),
            dict(DISCORD_BOT_TOKEN="", DISCORD_GUILD_ID=""),
        ]

        for cfg in cases:
            with override_settings(**cfg):
                self.assertFalse(discord_enabled())


class DiscordClientScheduledEventTests(TestCase):
    def setUp(self):
        self.client = DiscordClient()

    def _mock_request(self, event_id="987654321"):
        resp = MagicMock()
        resp.json.return_value = {
            "id": event_id,
            "name": "Test Event",
            "entity_type": 3,
        }
        return patch.object(self.client, "_request", return_value=resp)

    @override_settings(**DISCORD_SETTINGS)
    def test_payload_shape(self):
        start = dt(2026, 6, 1, 14, 0, tzinfo=UTC)
        end = dt(2026, 6, 1, 15, 0, tzinfo=UTC)

        with self._mock_request() as mock_req:
            self.client.create_scheduled_event(
                guild_id="123",
                name="My Event",
                description="A description",
                location="https://zoom.us/j/123",
                start_time=start,
                end_time=end,
            )

        self.assertEqual(
            mock_req.call_args.kwargs["json"],
            {
                "name": "My Event",
                "description": "A description",
                "entity_type": 3,
                "entity_metadata": {"location": "https://zoom.us/j/123"},
                "scheduled_start_time": "2026-06-01T14:00:00+00:00",
                "scheduled_end_time": "2026-06-01T15:00:00+00:00",
                "privacy_level": 2,
            },
        )

    @override_settings(**DISCORD_SETTINGS)
    def test_sends_fields_unchanged(self):
        start = dt(2026, 6, 1, 14, 0, tzinfo=UTC)
        end = dt(2026, 6, 1, 15, 0, tzinfo=UTC)

        with self._mock_request() as mock_req:
            self.client.create_scheduled_event(
                guild_id="123",
                name="x" * 200,
                description="y" * 2000,
                location="z" * 200,
                start_time=start,
                end_time=end,
            )

        payload = mock_req.call_args.kwargs["json"]

        self.assertEqual(len(payload["name"]), 200)
        self.assertEqual(len(payload["description"]), 2000)
        self.assertEqual(len(payload["entity_metadata"]["location"]), 200)

    @override_settings(**DISCORD_SETTINGS)
    def test_handles_null_description(self):
        start = dt(2026, 6, 1, 14, 0, tzinfo=UTC)
        end = dt(2026, 6, 1, 15, 0, tzinfo=UTC)

        with self._mock_request() as mock_req:
            self.client.create_scheduled_event(
                guild_id="123",
                name="x",
                description=None,
                location="https://zoom.us/j/1",
                start_time=start,
                end_time=end,
            )

        self.assertEqual(mock_req.call_args.kwargs["json"]["description"], "")

    @override_settings(**DISCORD_SETTINGS)
    def test_sends_patch_to_scoped_event_url(self):
        with self._mock_request() as mock_req:
            self.client.modify_scheduled_event(
                guild_id="123",
                event_id="event-1",
                payload={"name": "Renamed"},
            )

        self.assertEqual(
            mock_req.call_args.args,
            ("PATCH", "/guilds/123/scheduled-events/event-1"),
        )

    @override_settings(**DISCORD_SETTINGS)
    def test_forwards_payload_unchanged(self):
        payload = {
            "name": "Renamed",
            "entity_metadata": {"location": "https://zoom.us/j/999"},
        }

        with self._mock_request() as mock_req:
            self.client.modify_scheduled_event(
                guild_id="123",
                event_id="event-1",
                payload=payload,
            )

        self.assertEqual(mock_req.call_args.kwargs["json"], payload)

    @override_settings(**DISCORD_SETTINGS)
    def test_returns_updated_event_json(self):
        with self._mock_request(event_id="event-1") as mock_req:
            result = self.client.modify_scheduled_event(
                guild_id="123",
                event_id="event-1",
                payload={"name": "Renamed"},
            )

        self.assertEqual(result, mock_req.return_value.json.return_value)


class DiscordClientRequestTests(TestCase):
    def setUp(self):
        self.client = DiscordClient()

    @override_settings(**DISCORD_SETTINGS)
    def test_sets_bot_authorization_header(self):
        resp = MagicMock(status_code=200)
        resp.raise_for_status.return_value = None

        with patch.object(
            self.client.session, "request", return_value=resp
        ) as mock_req:
            self.client._request("GET", "/foo")

        headers = mock_req.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bot bot-token")

    @override_settings(**DISCORD_SETTINGS)
    def test_logs_on_429(self):
        resp = MagicMock(status_code=429)
        resp.raise_for_status.side_effect = Exception("429")

        with patch.object(self.client.session, "request", return_value=resp):
            with self.assertLogs("home.integrations.discord.client", level="ERROR"):
                with self.assertRaises(Exception):
                    self.client._request("GET", "/foo")

    @override_settings(**DISCORD_SETTINGS)
    def test_logs_response_body_and_reraises_on_http_error(self):
        resp = MagicMock(status_code=500)
        resp.text = "boom"
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)

        with patch.object(self.client.session, "request", return_value=resp):
            with self.assertLogs(
                "home.integrations.discord.client", level="ERROR"
            ) as logs:
                with self.assertRaises(requests.HTTPError):
                    self.client._request("GET", "/foo")

        self.assertIn("boom", "\n".join(logs.output))


class PrepareFieldsTests(TestCase):
    def _event(self, **kwargs):
        defaults = {"title": "My Event", "zoom_link": "https://zoom.us/j/1"}
        defaults.update(kwargs)
        return EventFactory.build(**defaults)

    def test_returns_fields_unchanged_when_within_limits(self):
        result = _prepare_fields(self._event(description="A description"))
        self.assertEqual(
            result,
            ("My Event", "A description", "https://zoom.us/j/1"),
        )

    def test_passes_through_title_and_description_without_truncating(self):
        """Name/description caps are enforced on the model, so the service no
        longer truncates them; it passes whatever it's given straight through."""
        event = self._event(title="x" * 200, description="y" * 2000)

        name, description, _ = _prepare_fields(event)

        self.assertEqual(len(name), 200)
        self.assertEqual(len(description), 2000)

    def test_raises_on_over_long_zoom_link(self):
        event = self._event(zoom_link="https://zoom.us/j/" + "z" * 100)
        with self.assertRaises(ValueError):
            _prepare_fields(event)


class UpdateEventTests(TestCase):
    """Service-level update_event: the payload sent to Discord mirrors the
    create path, but as a PATCH targeting the stored discord_event_id."""

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.integrations.discord.service.discord_client")
    def test_builds_expected_modify_payload(self, mock_client):
        event = EventFactory.build(
            title="My Event",
            description="A description",
            zoom_link="https://zoom.us/j/123",
            discord_event_id="discord-456",
            start_time=dt(2026, 6, 1, 14, 0, tzinfo=UTC),
        )

        update_event(event)

        mock_client.modify_scheduled_event.assert_called_once_with(
            guild_id="123456789",
            event_id="discord-456",
            payload={
                "name": "My Event",
                "description": "A description",
                "entity_metadata": {"location": "https://zoom.us/j/123"},
                "scheduled_start_time": "2026-06-01T14:00:00+00:00",
                "scheduled_end_time": "2026-06-01T15:00:00+00:00",
            },
        )

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.integrations.discord.service.discord_client")
    def test_raises_on_over_long_zoom_link_without_calling_discord(self, mock_client):
        event = EventFactory.build(
            title="My Event",
            zoom_link="https://zoom.us/j/" + "z" * 100,
            discord_event_id="discord-456",
            start_time=dt(2026, 6, 1, 14, 0, tzinfo=UTC),
        )

        with self.assertRaises(ValueError):
            update_event(event)

        mock_client.modify_scheduled_event.assert_not_called()


class SyncEventDiscordTests(TestCase):
    """Discord behaviour of the single sync_event task (create and update paths).

    Zoom is left unconfigured so these exercise the Discord branch in isolation;
    each event carries a pre-set zoom_link (Discord requires it as a location).
    """

    @override_settings(DISCORD_BOT_TOKEN="", DISCORD_GUILD_ID="")
    @patch("home.tasks.sync_event.create_event")
    def test_skips_when_discord_not_configured(self, mock_create):
        event = EventFactory.create(zoom_link="https://zoom.us/j/abc")

        sync_event.call(event_id=event.pk)

        mock_create.assert_not_called()

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.tasks.sync_event.create_event")
    def test_handles_missing_event(self, mock_create):
        sync_event.call(event_id=999999)

        mock_create.assert_not_called()

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.tasks.sync_event.create_event")
    def test_creates_event_and_writes_id(self, mock_create):
        mock_create.return_value = "discord-id-42"
        event = EventFactory.create(zoom_link="https://zoom.us/j/abc")

        sync_event.call(event_id=event.pk)

        event.refresh_from_db()
        self.assertEqual(event.discord_event_id, "discord-id-42")
        self.assertIsNotNone(event.discord_synced_at)

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.tasks.sync_event.create_event")
    def test_skips_when_zoom_link_missing(self, mock_create):
        event = EventFactory.create(zoom_link="")

        sync_event.call(event_id=event.pk)

        mock_create.assert_not_called()

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.tasks.sync_event.update_event")
    def test_updates_when_discord_event_id_present(self, mock_update):
        event = EventFactory.create(
            zoom_link="https://zoom.us/j/existing",
            discord_event_id="discord-456",
        )

        sync_event.call(event_id=event.pk)

        mock_update.assert_called_once()
        event.refresh_from_db()
        self.assertIsNotNone(event.discord_synced_at)

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.tasks.sync_event.create_event")
    def test_create_error_leaves_id_empty(self, mock_create):
        mock_create.side_effect = Exception("Discord API down")
        event = EventFactory.create(zoom_link="https://zoom.us/j/abc")

        sync_event.call(event_id=event.pk)

        event.refresh_from_db()
        self.assertEqual(event.discord_event_id, "")
        self.assertIsNone(event.discord_synced_at)


class SyncEventZoomThenDiscordTests(TestCase):
    """The single task creates the Zoom meeting, then the Discord event in the
    same run — the Zoom link set in-memory is visible to the Discord step."""

    @override_settings(**ZOOM_SETTINGS, **DISCORD_SETTINGS)
    @patch("home.tasks.sync_event.create_event")
    @patch("home.tasks.sync_event.create_event_meeting")
    def test_one_run_creates_both(self, mock_zoom, mock_discord):
        mock_zoom.return_value = ZoomMeeting("https://zoom.us/j/x", "999")
        mock_discord.return_value = "discord-1"
        event = EventFactory.create(zoom_link="")

        sync_event.call(event_id=event.pk)

        event.refresh_from_db()
        self.assertEqual(event.zoom_link, "https://zoom.us/j/x")
        self.assertEqual(event.zoom_meeting_id, "999")
        self.assertEqual(event.discord_event_id, "discord-1")
        mock_discord.assert_called_once()
