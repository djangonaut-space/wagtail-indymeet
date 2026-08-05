"""
Tests for Discord integration: DiscordClient, the discord service
(create/update event, _prepare_fields), and the Discord behaviour of sync_event
(including the combined Zoom-then-Discord run in a single task).
"""

import json
from datetime import datetime as dt
from datetime import timezone as dt_timezone
from unittest.mock import patch

import requests
import responses as rsps
from django.test import TestCase, override_settings

from home.factories import EventFactory
from home.integrations.discord.client import BASE_URL, DiscordClient
from home.integrations.discord.service import (
    MESSAGE_CONTENT_MAX,
    _prepare_fields,
    create_message,
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
    def test_true_with_credentials(self):
        with override_settings(**DISCORD_SETTINGS):
            self.assertTrue(discord_enabled())

    def test_false_missing_credential(self):
        cases = [
            dict(DISCORD_BOT_TOKEN="", DISCORD_GUILD_ID="123"),
            dict(DISCORD_BOT_TOKEN="tok", DISCORD_GUILD_ID=""),
            dict(DISCORD_BOT_TOKEN="", DISCORD_GUILD_ID=""),
        ]

        for cfg in cases:
            with override_settings(**cfg):
                self.assertFalse(discord_enabled())


class DiscordClientScheduledEventTests(TestCase):
    """DiscordClient scheduled-event methods, over HTTP stubbed with responses.

    The real client, payload serialization, and URL construction run against
    the stubbed endpoints; assertions read the request body responses captured.
    """

    def setUp(self):
        self.client = DiscordClient()

    @override_settings(**DISCORD_SETTINGS)
    @rsps.activate
    def test_create_payload(self):
        start = dt(2026, 6, 1, 14, 0, tzinfo=UTC)
        end = dt(2026, 6, 1, 15, 0, tzinfo=UTC)
        rsps.add(
            rsps.POST,
            f"{BASE_URL}/guilds/123/scheduled-events",
            json={"id": "987654321"},
        )

        self.client.create_scheduled_event(
            guild_id="123",
            name="My Event",
            description="A description",
            location="https://zoom.us/j/123",
            start_time=start,
            end_time=end,
        )

        self.assertEqual(
            json.loads(rsps.calls[0].request.body),
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
    @rsps.activate
    def test_create_long_fields(self):
        """Name/description/location aren't truncated, even at Discord's own
        length limits."""
        start = dt(2026, 6, 1, 14, 0, tzinfo=UTC)
        end = dt(2026, 6, 1, 15, 0, tzinfo=UTC)
        rsps.add(
            rsps.POST,
            f"{BASE_URL}/guilds/123/scheduled-events",
            json={"id": "987654321"},
        )

        self.client.create_scheduled_event(
            guild_id="123",
            name="x" * 200,
            description="y" * 2000,
            location="z" * 200,
            start_time=start,
            end_time=end,
        )

        payload = json.loads(rsps.calls[0].request.body)

        self.assertEqual(len(payload["name"]), 200)
        self.assertEqual(len(payload["description"]), 2000)
        self.assertEqual(len(payload["entity_metadata"]["location"]), 200)

    @override_settings(**DISCORD_SETTINGS)
    @rsps.activate
    def test_create_null_description(self):
        """A null description is sent to Discord as an empty string."""
        start = dt(2026, 6, 1, 14, 0, tzinfo=UTC)
        end = dt(2026, 6, 1, 15, 0, tzinfo=UTC)
        rsps.add(
            rsps.POST,
            f"{BASE_URL}/guilds/123/scheduled-events",
            json={"id": "987654321"},
        )

        self.client.create_scheduled_event(
            guild_id="123",
            name="x",
            description=None,
            location="https://zoom.us/j/1",
            start_time=start,
            end_time=end,
        )

        self.assertEqual(json.loads(rsps.calls[0].request.body)["description"], "")

    @override_settings(**DISCORD_SETTINGS)
    @rsps.activate
    def test_modify_payload(self):
        """PATCHes the guild-scoped event URL, forwarding the payload
        unchanged, and returns Discord's response JSON."""
        payload = {
            "name": "Renamed",
            "entity_metadata": {"location": "https://zoom.us/j/999"},
        }
        rsps.add(
            rsps.PATCH,
            f"{BASE_URL}/guilds/123/scheduled-events/event-1",
            json={"id": "event-1", "name": "Renamed"},
        )

        result = self.client.modify_scheduled_event(
            guild_id="123",
            event_id="event-1",
            payload=payload,
        )

        self.assertEqual(rsps.calls[0].request.method, "PATCH")
        self.assertEqual(
            rsps.calls[0].request.url,
            f"{BASE_URL}/guilds/123/scheduled-events/event-1",
        )
        self.assertEqual(json.loads(rsps.calls[0].request.body), payload)
        self.assertEqual(result, {"id": "event-1", "name": "Renamed"})


class DiscordClientRequestTests(TestCase):
    """The shared _request helper: auth header, rate-limit logging, and error
    handling, exercised over HTTP stubbed with responses."""

    def setUp(self):
        self.client = DiscordClient()

    @override_settings(**DISCORD_SETTINGS)
    @rsps.activate
    def test_auth_header(self):
        rsps.add(rsps.GET, f"{BASE_URL}/foo", json={})

        self.client._request("GET", "/foo")

        self.assertEqual(
            rsps.calls[0].request.headers["Authorization"], "Bot bot-token"
        )

    @override_settings(**DISCORD_SETTINGS)
    @rsps.activate
    def test_http_error(self):
        """Logs the response body, then re-raises."""
        rsps.add(rsps.GET, f"{BASE_URL}/foo", status=403, body="boom")

        with self.assertLogs("home.integrations.discord.client", level="ERROR") as logs:
            with self.assertRaises(requests.HTTPError):
                self.client._request("GET", "/foo")

        self.assertIn("boom", "\n".join(logs.output))


class PrepareFieldsTests(TestCase):
    def _event(self, **kwargs):
        defaults = {"title": "My Event", "zoom_link": "https://zoom.us/j/1"}
        defaults.update(kwargs)
        return EventFactory.build(**defaults)

    def test_within_limits(self):
        result = _prepare_fields(self._event(description="A description"))
        self.assertEqual(
            result,
            ("My Event", "A description", "https://zoom.us/j/1"),
        )

    def test_no_truncation(self):
        """Name/description caps are enforced on the model, so the service no
        longer truncates them; it passes whatever it's given straight through."""
        event = self._event(title="x" * 200, description="y" * 2000)

        name, description, _ = _prepare_fields(event)

        self.assertEqual(len(name), 200)
        self.assertEqual(len(description), 2000)

    def test_long_zoom_link_raises(self):
        event = self._event(zoom_link="https://zoom.us/j/" + "z" * 100)
        with self.assertRaises(ValueError):
            _prepare_fields(event)


class UpdateEventTests(TestCase):
    """Service-level update_event: the payload sent to Discord mirrors the
    create path, but as a PATCH targeting the stored discord_event_id.

    Discord is stubbed at the HTTP layer so the real client, payload
    serialization, and URL construction are exercised end to end.
    """

    @override_settings(**DISCORD_SETTINGS)
    @rsps.activate
    def test_payload(self):
        event = EventFactory.build(
            title="My Event",
            description="A description",
            zoom_link="https://zoom.us/j/123",
            discord_event_id="discord-456",
            start_time=dt(2026, 6, 1, 14, 0, tzinfo=UTC),
        )
        rsps.add(
            rsps.PATCH,
            f"{BASE_URL}/guilds/123456789/scheduled-events/discord-456",
            json={"id": "discord-456"},
        )

        update_event(event)

        self.assertEqual(
            json.loads(rsps.calls[0].request.body),
            {
                "name": "My Event",
                "description": "A description",
                "entity_metadata": {"location": "https://zoom.us/j/123"},
                "scheduled_start_time": "2026-06-01T14:00:00+00:00",
                "scheduled_end_time": "2026-06-01T15:00:00+00:00",
            },
        )

    @override_settings(**DISCORD_SETTINGS)
    @rsps.activate
    def test_long_zoom_link_raises(self):
        """Validated before Discord is called, so no request is made."""
        event = EventFactory.build(
            title="My Event",
            zoom_link="https://zoom.us/j/" + "z" * 100,
            discord_event_id="discord-456",
            start_time=dt(2026, 6, 1, 14, 0, tzinfo=UTC),
        )

        with self.assertRaises(ValueError):
            update_event(event)

        self.assertEqual(len(rsps.calls), 0)


class CreateMessageTests(TestCase):
    @override_settings(**DISCORD_SETTINGS)
    @rsps.activate
    def test_posts_message_to_channel(self):
        rsps.add(
            rsps.POST,
            f"{BASE_URL}/channels/chan-1/messages",
            json={"id": "1", "content": "hi"},
        )

        result = create_message(channel="chan-1", message="hi")

        self.assertEqual(json.loads(rsps.calls[0].request.body), {"content": "hi"})
        self.assertEqual(result, {"id": "1", "content": "hi"})

    @override_settings(**DISCORD_SETTINGS)
    @rsps.activate
    def test_raises_on_over_long_message(self):
        with self.assertRaises(ValueError):
            create_message(channel="chan-1", message="x" * (MESSAGE_CONTENT_MAX + 1))

        self.assertEqual(len(rsps.calls), 0)


class SyncEventDiscordTests(TestCase):
    """Discord behaviour of the single sync_event task (create and update paths).

    Zoom is left unconfigured so these exercise the Discord branch in isolation;
    each event carries a pre-set zoom_link (Discord requires it as a location).
    """

    @override_settings(DISCORD_BOT_TOKEN="", DISCORD_GUILD_ID="")
    @patch("home.tasks.sync_event.create_event")
    def test_skips_unconfigured(self, mock_create):
        event = EventFactory.create(zoom_link="https://zoom.us/j/abc")

        sync_event.call(event_id=event.pk)

        mock_create.assert_not_called()

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.tasks.sync_event.create_event")
    def test_missing_event(self, mock_create):
        sync_event.call(event_id=999999)

        mock_create.assert_not_called()

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.tasks.sync_event.create_event")
    def test_create(self, mock_create):
        mock_create.return_value = "discord-id-42"
        event = EventFactory.create(zoom_link="https://zoom.us/j/abc")

        sync_event.call(event_id=event.pk)

        event.refresh_from_db()
        self.assertEqual(event.discord_event_id, "discord-id-42")
        self.assertIsNotNone(event.discord_synced_at)

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.tasks.sync_event.create_event")
    def test_skips_no_zoom_link(self, mock_create):
        event = EventFactory.create(zoom_link="")

        sync_event.call(event_id=event.pk)

        mock_create.assert_not_called()

    @override_settings(**DISCORD_SETTINGS)
    @patch("home.tasks.sync_event.update_event")
    def test_update(self, mock_update):
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
    def test_create_error(self, mock_create):
        """A failed create leaves discord_event_id/synced_at unset."""
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
    def test_creates_both(self, mock_zoom, mock_discord):
        mock_zoom.return_value = ZoomMeeting("https://zoom.us/j/x", "999")
        mock_discord.return_value = "discord-1"
        event = EventFactory.create(zoom_link="")

        sync_event.call(event_id=event.pk)

        event.refresh_from_db()
        self.assertEqual(event.zoom_link, "https://zoom.us/j/x")
        self.assertEqual(event.zoom_meeting_id, "999")
        self.assertEqual(event.discord_event_id, "discord-1")
        mock_discord.assert_called_once()
