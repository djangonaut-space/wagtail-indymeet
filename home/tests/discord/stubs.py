"""
An in-memory Discord REST API for tests, served via the responses library.

``stub_discord_api()`` registers every endpoint the session setup/teardown
actions use, so tests exercise the real ``DiscordClient`` over stubbed HTTP
instead of patching it. The inspection helpers parse ``responses.calls``
back into the shapes tests assert on (payloads by channel name, member
updates by user id, ...).
"""

import json
import re
from urllib.parse import parse_qs, urlparse

import responses as rsps

from home.integrations.discord.client import BASE_URL

GUILD_ID = "guild-1"
GUILD_URL = f"{BASE_URL}/guilds/{GUILD_ID}"

BOT_ROLE_ID = "r-bot"

STANDING_GUILD_ROLES = [
    {"id": "guild-1", "name": "@everyone"},
    {"id": BOT_ROLE_ID, "name": "Djangonaut Bot"},
    {"id": "r-dj", "name": "Djangonauts"},
    {"id": "r-cap", "name": "Captains"},
    {"id": "r-nav", "name": "Navigators"},
    {"id": "r-org", "name": "Session Organizers"},
    {"id": "r-adm", "name": "Admins"},
    {"id": "r-adv", "name": "Advisors"},
]


def member(member_id, username, roles=()):
    """A guild member dict as Discord returns them."""
    return {"user": {"id": member_id, "username": username}, "roles": list(roles)}


def _endpoint(method, url):
    """Register the decorated function as the handler for ``method url``."""

    def register(func):
        rsps.add_callback(method, url, callback=func)
        return func

    return register


def stub_discord_api(
    *,
    roles=None,
    channels=(),
    guild_members=(),
    member_search=None,
    fail_create_channels=(),
    fail_update_channels=None,
    fail_delete_channels=(),
    fail_update_members=(),
):
    """Register the Discord endpoints the session actions call.

    ``member_search`` maps a casefolded query to the member dicts returned
    for it. Created roles/channels get sequential ids (``new-role-1``,
    ``new-channel-1``, ...). Failures are injected per channel name
    (creates), per channel id -> status code (updates), per channel id
    (deletes), or per user id (guild-member updates).
    """
    roles = list(STANDING_GUILD_ROLES if roles is None else roles)
    counters = {"role": 0, "channel": 0}
    channel_path = re.compile(rf"{re.escape(BASE_URL)}/channels/[^/]+$")
    member_path = re.compile(rf"{re.escape(GUILD_URL)}/members/[^/]+$")

    @_endpoint(rsps.GET, f"{GUILD_URL}/roles")
    def get_roles(request):
        return 200, {}, json.dumps(roles)

    @_endpoint(rsps.POST, f"{GUILD_URL}/roles")
    def create_role(request):
        counters["role"] += 1
        payload = json.loads(request.body)
        return 200, {}, json.dumps({"id": f"new-role-{counters['role']}", **payload})

    @_endpoint(rsps.GET, f"{GUILD_URL}/channels")
    def get_channels(request):
        return 200, {}, json.dumps(list(channels))

    @_endpoint(rsps.POST, f"{GUILD_URL}/channels")
    def create_channel(request):
        payload = json.loads(request.body)
        if payload["name"] in fail_create_channels:
            return 403, {}, "{}"
        counters["channel"] += 1
        return (
            200,
            {},
            json.dumps({"id": f"new-channel-{counters['channel']}", **payload}),
        )

    @_endpoint(rsps.PATCH, channel_path)
    def update_channel(request):
        channel_id = urlparse(request.url).path.rsplit("/", 1)[-1]
        status = (fail_update_channels or {}).get(channel_id)
        if status:
            return status, {}, "{}"
        payload = json.loads(request.body)
        return 200, {}, json.dumps({"id": channel_id, **payload})

    @_endpoint(rsps.DELETE, channel_path)
    def delete_channel(request):
        channel_id = urlparse(request.url).path.rsplit("/", 1)[-1]
        if channel_id in fail_delete_channels:
            return 403, {}, "{}"
        return 204, {}, ""

    @_endpoint(rsps.GET, f"{GUILD_URL}/members/search")
    def search_members(request):
        query = parse_qs(urlparse(request.url).query)["query"][0]
        return 200, {}, json.dumps((member_search or {}).get(query.casefold(), []))

    @_endpoint(rsps.GET, f"{GUILD_URL}/members")
    def list_members(request):
        return 200, {}, json.dumps(list(guild_members))

    @_endpoint(rsps.PATCH, member_path)
    def update_member(request):
        user_id = urlparse(request.url).path.rsplit("/", 1)[-1]
        if user_id in fail_update_members:
            return 403, {}, "{}"
        return 200, {}, "{}"


def _path(call) -> str:
    return urlparse(call.request.url).path


def _body(call) -> dict:
    return json.loads(call.request.body)


def channel_creations() -> dict[str, dict]:
    """POSTed channel payloads, keyed by channel name."""
    return {
        _body(call)["name"]: _body(call)
        for call in rsps.calls
        if call.request.method == "POST" and _path(call).endswith("/channels")
    }


def channel_updates() -> dict[str, dict]:
    """PATCHed channel payloads, keyed by channel id."""
    return {
        _path(call).rsplit("/", 1)[-1]: _body(call)
        for call in rsps.calls
        if call.request.method == "PATCH" and "/channels/" in _path(call)
    }


def channel_deletions() -> list[str]:
    """Ids of DELETEd channels, in call order."""
    return [
        _path(call).rsplit("/", 1)[-1]
        for call in rsps.calls
        if call.request.method == "DELETE" and "/channels/" in _path(call)
    ]


def role_creations() -> list[str]:
    """Names of POSTed guild roles, in call order."""
    return [
        _body(call)["name"]
        for call in rsps.calls
        if call.request.method == "POST" and _path(call).endswith("/roles")
    ]


def member_role_updates() -> dict[str, dict]:
    """PATCHed guild-member payloads, keyed by user id."""
    return {
        _path(call).rsplit("/", 1)[-1]: _body(call)
        for call in rsps.calls
        if call.request.method == "PATCH"
        and "/members/" in _path(call)
        and "/roles/" not in _path(call)
    }
