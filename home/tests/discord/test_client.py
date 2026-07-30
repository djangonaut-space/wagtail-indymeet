"""
Tests for the DiscordClient guild/channel/role methods used by the
session setup/teardown admin actions, over HTTP stubbed with responses.
"""

import json
from urllib.parse import parse_qs, urlparse

import responses as rsps
from django.test import TestCase

from home.integrations.discord.client import (
    BASE_URL,
    CATEGORY_TYPE,
    TEXT_CHANNEL_TYPE,
    DiscordClient,
)


def request_json(call) -> dict:
    return json.loads(call.request.body)


def request_params(call) -> dict:
    return parse_qs(urlparse(call.request.url).query)


class DiscordClientSessionMethodsTests(TestCase):
    def setUp(self):
        self.client = DiscordClient()

    def test_retries_put_requests(self):
        """Role assignment uses PUT; a 429 there must be retried like the rest."""
        retry = self.client.session.get_adapter("https://").max_retries
        self.assertIn("PUT", retry.allowed_methods)

    @rsps.activate
    def test_get_guild_roles(self):
        rsps.add(
            rsps.GET,
            f"{BASE_URL}/guilds/123/roles",
            json=[{"id": "1", "name": "Navigators"}],
        )

        roles = self.client.get_guild_roles(guild_id="123")

        self.assertEqual(roles, [{"id": "1", "name": "Navigators"}])
        self.assertEqual(
            rsps.calls[0].request.headers["Authorization"], "Bot bot-token"
        )

    @rsps.activate
    def test_create_guild_role(self):
        rsps.add(
            rsps.POST,
            f"{BASE_URL}/guilds/123/roles",
            json={"id": "9", "name": "Team Bee"},
        )

        role = self.client.create_guild_role(guild_id="123", name="Team Bee")

        self.assertEqual(role["id"], "9")
        self.assertEqual(request_json(rsps.calls[0]), {"name": "Team Bee"})

    @rsps.activate
    def test_search_guild_members(self):
        rsps.add(
            rsps.GET,
            f"{BASE_URL}/guilds/123/members/search",
            json=[{"user": {"id": "5"}}],
        )

        members = self.client.search_guild_members(guild_id="123", query="novauser1")

        self.assertEqual(members, [{"user": {"id": "5"}}])
        self.assertEqual(
            request_params(rsps.calls[0]), {"query": ["novauser1"], "limit": ["10"]}
        )

    @rsps.activate
    def test_list_guild_members_first_page(self):
        rsps.add(rsps.GET, f"{BASE_URL}/guilds/123/members", json=[])

        self.client.list_guild_members(guild_id="123")

        self.assertEqual(request_params(rsps.calls[0]), {"limit": ["1000"]})

    @rsps.activate
    def test_list_guild_members_passes_after_cursor(self):
        rsps.add(rsps.GET, f"{BASE_URL}/guilds/123/members", json=[])

        self.client.list_guild_members(guild_id="123", limit=5, after="42")

        self.assertEqual(
            request_params(rsps.calls[0]), {"limit": ["5"], "after": ["42"]}
        )

    @rsps.activate
    def test_modify_guild_member(self):
        rsps.add(
            rsps.PATCH,
            f"{BASE_URL}/guilds/123/members/7",
            json={"roles": ["1", "2"]},
        )

        updated = self.client.modify_guild_member(
            guild_id="123", user_id="7", payload={"roles": ["1", "2"]}
        )

        self.assertEqual(updated, {"roles": ["1", "2"]})
        self.assertEqual(request_json(rsps.calls[0]), {"roles": ["1", "2"]})

    @rsps.activate
    def test_add_member_role(self):
        rsps.add(rsps.PUT, f"{BASE_URL}/guilds/123/members/7/roles/9", status=204)

        self.client.add_member_role(guild_id="123", user_id="7", role_id="9")

        self.assertEqual(len(rsps.calls), 1)

    @rsps.activate
    def test_remove_member_role(self):
        rsps.add(rsps.DELETE, f"{BASE_URL}/guilds/123/members/7/roles/9", status=204)

        self.client.remove_member_role(guild_id="123", user_id="7", role_id="9")

        self.assertEqual(len(rsps.calls), 1)

    @rsps.activate
    def test_get_guild_channels(self):
        rsps.add(
            rsps.GET,
            f"{BASE_URL}/guilds/123/channels",
            json=[{"id": "11", "type": CATEGORY_TYPE}],
        )

        channels = self.client.get_guild_channels(guild_id="123")

        self.assertEqual(channels, [{"id": "11", "type": CATEGORY_TYPE}])

    @rsps.activate
    def test_create_guild_channel_category(self):
        """Categories have no parent or overwrites; those keys must be omitted."""
        rsps.add(rsps.POST, f"{BASE_URL}/guilds/123/channels", json={"id": "11"})

        self.client.create_guild_channel(
            guild_id="123", name="Session 2026", channel_type=CATEGORY_TYPE
        )

        self.assertEqual(
            request_json(rsps.calls[0]),
            {"name": "Session 2026", "type": CATEGORY_TYPE},
        )

    @rsps.activate
    def test_create_guild_channel_text_with_overwrites(self):
        overwrites = [{"id": "123", "type": 0, "deny": "1024", "allow": "0"}]
        rsps.add(rsps.POST, f"{BASE_URL}/guilds/123/channels", json={"id": "12"})

        self.client.create_guild_channel(
            guild_id="123",
            name="team-bee",
            channel_type=TEXT_CHANNEL_TYPE,
            parent_id="11",
            permission_overwrites=overwrites,
        )

        self.assertEqual(
            request_json(rsps.calls[0]),
            {
                "name": "team-bee",
                "type": TEXT_CHANNEL_TYPE,
                "parent_id": "11",
                "permission_overwrites": overwrites,
            },
        )

    @rsps.activate
    def test_create_guild_channel_with_topic_and_thread_archive_duration(self):
        rsps.add(rsps.POST, f"{BASE_URL}/guilds/123/channels", json={"id": "12"})

        self.client.create_guild_channel(
            guild_id="123",
            name="captains-and-navigators",
            channel_type=TEXT_CHANNEL_TYPE,
            topic="Ask each other questions.",
            default_auto_archive_duration=10080,
        )

        self.assertEqual(
            request_json(rsps.calls[0]),
            {
                "name": "captains-and-navigators",
                "type": TEXT_CHANNEL_TYPE,
                "topic": "Ask each other questions.",
                "default_auto_archive_duration": 10080,
            },
        )

    @rsps.activate
    def test_create_guild_channel_omits_blank_topic_and_unset_archive_duration(self):
        rsps.add(rsps.POST, f"{BASE_URL}/guilds/123/channels", json={"id": "12"})

        self.client.create_guild_channel(
            guild_id="123", name="team-bee-voice", channel_type=TEXT_CHANNEL_TYPE
        )

        self.assertEqual(
            request_json(rsps.calls[0]),
            {"name": "team-bee-voice", "type": TEXT_CHANNEL_TYPE},
        )

    @rsps.activate
    def test_delete_channel(self):
        rsps.add(rsps.DELETE, f"{BASE_URL}/channels/12", status=204)

        self.client.delete_channel(channel_id="12")

        self.assertEqual(len(rsps.calls), 1)

    @rsps.activate
    def test_modify_channel(self):
        payload = {"name": "team-bee", "permission_overwrites": []}
        rsps.add(rsps.PATCH, f"{BASE_URL}/channels/12", json={"id": "12"})

        channel = self.client.modify_channel(channel_id="12", payload=payload)

        self.assertEqual(channel, {"id": "12"})
        self.assertEqual(request_json(rsps.calls[0]), payload)
