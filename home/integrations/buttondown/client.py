import logging

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE_URL = "https://api.buttondown.email/v1"


class ButtondownClient:
    """Low-level Buttondown API client."""

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
        """Send an authenticated request to Buttondown."""
        kwargs.setdefault("timeout", 10)
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Token {settings.BUTTONDOWN_API_KEY}"
        url = f"{BASE_URL}{path}"
        try:
            response = self.session.request(method, url, headers=headers, **kwargs)
            if response.status_code == 429:
                logger.error("Buttondown rate limit exceeded")
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            if not (
                isinstance(exc, requests.HTTPError)
                and exc.response is not None
                and exc.response.status_code == 404
            ):
                logger.exception("Buttondown API request failed: %s %s", method, url)
            raise

    def get_subscriber_by_email(self, email: str) -> dict | None:
        """
        Look up a subscriber by email address.

        Returns the subscriber dict if found, or None if not found.
        """
        try:
            response = self._request("GET", f"/subscribers/{email}")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise
        return response.json()

    def create_subscriber(self, email: str, tags: list[str]) -> dict:
        """
        Create a new subscriber.

        Returns the created subscriber dict (including 'id' UUID).
        """
        response = self._request(
            "POST",
            "/subscribers",
            json={"email_address": email, "tags": tags, "type": "regular"},
        )
        return response.json()

    def patch_subscriber(self, subscriber_id: str, payload: dict) -> dict:
        """
        Partially update a subscriber.

        Returns the updated subscriber dict.
        """
        response = self._request(
            "PATCH",
            f"/subscribers/{subscriber_id}",
            json=payload,
        )
        return response.json()

    def delete_subscriber(self, subscriber_id: str) -> None:
        """Delete a subscriber from Buttondown (204 No Content on success)."""
        self._request("DELETE", f"/subscribers/{subscriber_id}")
