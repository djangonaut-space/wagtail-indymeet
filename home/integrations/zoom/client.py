import logging
from datetime import datetime, timezone as dt_timezone

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE_URL = "https://api.zoom.us/v2"
TOKEN_URL = "https://zoom.us/oauth/token"
TOKEN_CACHE_KEY = "zoom_access_token"


class ZoomClient:
    """Low-level Zoom API client."""

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

    def _get_access_token(self) -> str:
        """Get OAuth token (cached)."""
        token = cache.get(TOKEN_CACHE_KEY)

        if token:
            return token

        response = self.session.post(
            TOKEN_URL,
            data={
                "grant_type": "account_credentials",
                "account_id": settings.ZOOM_ACCOUNT_ID,
            },
            auth=(settings.ZOOM_CLIENT_ID, settings.ZOOM_CLIENT_SECRET),
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        token = data["access_token"]
        expires = data.get("expires_in", 3600)

        cache.set(TOKEN_CACHE_KEY, token, expires - 60)

        return token

    def _request(
        self, method: str, url: str, retry_auth: bool = True, **kwargs
    ) -> requests.Response:
        """Send request with automatic auth + retry."""
        kwargs.setdefault("timeout", 10)

        token = self._get_access_token()

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                **kwargs,
            )

            # Token expired → refresh and retry once
            if response.status_code == 401 and retry_auth:
                logger.info("Zoom token expired, refreshing")

                cache.delete(TOKEN_CACHE_KEY)

                new_token = self._get_access_token()
                headers["Authorization"] = f"Bearer {new_token}"

                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs,
                )

            if response.status_code == 429:
                logger.error("Zoom rate limit exceeded")

            response.raise_for_status()

            return response

        except requests.RequestException:
            logger.exception("Zoom API request failed: %s %s", method, url)
            raise

    def create_meeting(
        self,
        topic: str,
        start_time: datetime,
        duration_minutes: int,
        user_id: str = "me",
    ) -> dict:
        """Create a Zoom meeting."""

        if timezone.is_aware(start_time):
            start_time = timezone.localtime(start_time, dt_timezone.utc)

        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        duration_minutes = max(1, min(duration_minutes, 1440))

        payload = {
            "topic": topic,
            "type": 2,
            "start_time": start_str,
            "duration": duration_minutes,
            "timezone": "UTC",
            "default_password": True,
        }

        payload["settings"] = {
            "mute_upon_entry": True,
            "waiting_room": True,
            "host_video": True,
            "participant_video": True,
            "join_before_host": False,
        }

        url = f"{BASE_URL}/users/{user_id}/meetings"

        response = self._request(
            "POST",
            url,
            json=payload,
        )

        data = response.json()

        return {
            "id": data["id"],
            "join_url": data["join_url"],
            "start_url": data["start_url"],
        }
