import logging

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE_URL = "https://discord.com/api/v10"

# Discord channel types.
# https://discord.com/developers/docs/resources/channel#channel-object-channel-types
TEXT_CHANNEL_TYPE = 0
VOICE_CHANNEL_TYPE = 2
CATEGORY_TYPE = 4

# Permission overwrite target types.
# https://discord.com/developers/docs/resources/channel#overwrite-object
ROLE_OVERWRITE = 0
MEMBER_OVERWRITE = 1

# Permission bits.
# https://discord.com/developers/docs/topics/permissions
VIEW_CHANNEL = 1 << 10
ADD_REACTIONS = 1 << 6
SEND_MESSAGES = 1 << 11
MANAGE_MESSAGES = 1 << 13
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
READ_MESSAGE_HISTORY = 1 << 16
USE_EXTERNAL_EMOJIS = 1 << 18
MANAGE_THREADS = 1 << 34
CREATE_PUBLIC_THREADS = 1 << 35
CREATE_PRIVATE_THREADS = 1 << 36
USE_EXTERNAL_STICKERS = 1 << 37
SEND_MESSAGES_IN_THREADS = 1 << 38
SEND_VOICE_MESSAGES = 1 << 46
SEND_POLLS = 1 << 49
PIN_MESSAGES = 1 << 51


class DiscordClient:
    """Low-level Discord API client (bot-token auth)."""

    def __init__(self) -> None:
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        return session

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", 10)
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bot {settings.DISCORD_BOT_TOKEN}"
        url = f"{BASE_URL}{path}"
        try:
            response = self.session.request(method, url, headers=headers, **kwargs)
            if response.status_code == 429:
                logger.error("Discord rate limit exceeded")
            response.raise_for_status()
            return response
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else "<no body>"
            logger.error(
                "Discord API request failed: %s %s -> %s: %s",
                method,
                url,
                exc.response.status_code if exc.response is not None else "?",
                body,
            )
            raise

    def create_scheduled_event(
        self,
        *,
        guild_id: str,
        name: str,
        description: str,
        location: str,
        start_time,
        end_time,
    ) -> dict:
        """Create a Discord guild scheduled event.

        Registers an EXTERNAL scheduled event (one with a location string
        rather than a Discord voice/stage channel) on the given guild, visible
        to guild members only. Callers must ensure name/description/location
        already fit Discord's length limits. Returns the created event as JSON.
        """
        payload = {
            "name": name,
            "description": description or "",
            "entity_type": 3,  # EXTERNAL
            "entity_metadata": {"location": location},
            "scheduled_start_time": start_time.isoformat(),
            "scheduled_end_time": end_time.isoformat(),
            "privacy_level": 2,  # GUILD_ONLY
        }
        response = self._request(
            "POST", f"/guilds/{guild_id}/scheduled-events", json=payload
        )
        return response.json()

    def modify_scheduled_event(
        self,
        *,
        guild_id: str,
        event_id: str,
        payload: dict,
    ) -> dict:
        """Update an existing Discord guild scheduled event.

        Sends only the fields present in ``payload`` to Discord, leaving other
        fields unchanged. Returns the updated event as JSON.
        """
        response = self._request(
            "PATCH",
            f"/guilds/{guild_id}/scheduled-events/{event_id}",
            json=payload,
        )
        return response.json()

    def get_guild_roles(self, *, guild_id: str) -> list[dict]:
        """Return all roles on the guild, including the @everyone role."""
        response = self._request("GET", f"/guilds/{guild_id}/roles")
        return response.json()

    def create_guild_role(self, *, guild_id: str, name: str) -> dict:
        """Create a guild role with default permissions and return it as JSON.

        Roles created here inherit @everyone's permissions; they exist purely
        as channel-access markers, not permission grants.
        """
        response = self._request(
            "POST", f"/guilds/{guild_id}/roles", json={"name": name}
        )
        return response.json()

    def search_guild_members(
        self, *, guild_id: str, query: str, limit: int = 10
    ) -> list[dict]:
        """Search guild members whose username or nickname starts with ``query``.

        Unlike listing all guild members, this endpoint does not require the
        GUILD_MEMBERS privileged intent.
        """
        response = self._request(
            "GET",
            f"/guilds/{guild_id}/members/search",
            params={"query": query, "limit": limit},
        )
        return response.json()

    def list_guild_members(
        self, *, guild_id: str, limit: int = 1000, after: str | None = None
    ) -> list[dict]:
        """Return one page of guild members, ordered by user ID.

        Requires the GUILD_MEMBERS privileged intent to be enabled for the bot
        in the Discord developer portal. Pass the last member's user ID as
        ``after`` to fetch the next page; a page shorter than ``limit`` is the
        final page.
        """
        params: dict = {"limit": limit}
        if after is not None:
            params["after"] = after
        response = self._request("GET", f"/guilds/{guild_id}/members", params=params)
        return response.json()

    def modify_guild_member(
        self, *, guild_id: str, user_id: str, payload: dict
    ) -> dict:
        """Update a guild member and return the updated member as JSON.

        Passing ``{"roles": [...]}`` replaces the member's full role set in a
        single call, which is preferred over one add/remove call per role.
        """
        response = self._request(
            "PATCH", f"/guilds/{guild_id}/members/{user_id}", json=payload
        )
        return response.json()

    def add_member_role(self, *, guild_id: str, user_id: str, role_id: str) -> None:
        """Assign a role to a guild member. Idempotent: re-adding is a no-op."""
        self._request("PUT", f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}")

    def remove_member_role(self, *, guild_id: str, user_id: str, role_id: str) -> None:
        """Remove a role from a guild member. Idempotent when already absent."""
        self._request("DELETE", f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}")

    def get_guild_channels(self, *, guild_id: str) -> list[dict]:
        """Return all guild channels, including categories, with overwrites."""
        response = self._request("GET", f"/guilds/{guild_id}/channels")
        return response.json()

    def create_guild_channel(
        self,
        *,
        guild_id: str,
        name: str,
        channel_type: int,
        parent_id: str | None = None,
        permission_overwrites: list[dict] | None = None,
        topic: str = "",
        default_auto_archive_duration: int | None = None,
    ) -> dict:
        """Create a guild channel or category and return it as JSON.

        Use ``CATEGORY_TYPE``/``TEXT_CHANNEL_TYPE`` for ``channel_type``; text
        channels are nested under a category via ``parent_id``.
        """
        payload: dict = {"name": name, "type": channel_type}
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if permission_overwrites is not None:
            payload["permission_overwrites"] = permission_overwrites
        if topic:
            payload["topic"] = topic
        if default_auto_archive_duration is not None:
            payload["default_auto_archive_duration"] = default_auto_archive_duration
        response = self._request("POST", f"/guilds/{guild_id}/channels", json=payload)
        return response.json()

    def delete_channel(self, *, channel_id: str) -> None:
        """Permanently delete a channel. Irreversible; a repeat delete 404s."""
        self._request("DELETE", f"/channels/{channel_id}")

    def modify_channel(self, *, channel_id: str, payload: dict) -> dict:
        """Update a channel and return the updated channel as JSON.

        A ``permission_overwrites`` entry in ``payload`` replaces the
        channel's entire overwrite set atomically, so access can be granted
        and revoked in one call with no window where no one has access.
        """
        response = self._request("PATCH", f"/channels/{channel_id}", json=payload)
        return response.json()

    def create_message(self, *, channel_id: str, content: str) -> dict:
        """Post a message to a text channel and return the created message as JSON."""
        response = self._request(
            "POST", f"/channels/{channel_id}/messages", json={"content": content}
        )
        return response.json()
