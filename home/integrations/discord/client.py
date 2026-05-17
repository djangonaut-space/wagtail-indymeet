import logging

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE_URL = "https://discord.com/api/v10"


class DiscordClient:
    """Low-level Discord API client (bot-token auth)."""

    def __init__(self) -> None:
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PATCH", "DELETE"],
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
