"""Google Calendar provider using OAuth 2.0 + the free/busy API.

Busy times come from ``calendar.freebusy``: we learn only *when* a user is busy,
never event titles or details, and persist only start/end intervals. The
``calendar.events.readonly`` scope is requested solely because ``events.watch``
push notifications require it; the notifications carry no event data, only a
signal to re-query free/busy. Webhooks are optional (see
``GOOGLE_CALENDAR_WEBHOOK_ENABLED``); without them, sync runs via polling and
lazy refresh. Uses raw ``requests`` calls like the Zoom/Discord integrations.
"""

import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from availability.providers.base import CalendarProvider, CalendarSyncError

logger = logging.getLogger(__name__)

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
EVENTS_WATCH_URL = (
    "https://www.googleapis.com/calendar/v3/calendars/primary/events/watch"
)
CHANNELS_STOP_URL = "https://www.googleapis.com/calendar/v3/channels/stop"

SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar.freebusy",
    # Required for events.watch push notifications; we never read event details.
    "https://www.googleapis.com/auth/calendar.events.readonly",
]

# Refresh a little before actual expiry to avoid racing the boundary.
TOKEN_EXPIRY_SKEW = timedelta(seconds=60)
REQUEST_TIMEOUT = 10


def _session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def is_configured() -> bool:
    """Whether Google OAuth credentials are present in settings."""
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


def build_authorization_url(state: str, redirect_uri: str) -> str:
    """Build the Google consent-screen URL to redirect the user to."""
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # request a refresh token
        "prompt": "consent",  # ensure a refresh token is returned on re-auth
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTHORIZATION_URL}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str) -> dict:
    """Exchange an authorization code for tokens. Returns the token payload."""
    response = _session().post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not response.ok:
        raise CalendarSyncError(
            f"Google token exchange failed ({response.status_code}): {response.text}"
        )
    return response.json()


def fetch_account_email(access_token: str) -> str:
    """Look up the connected account's email for display (best-effort)."""
    try:
        response = _session().get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=REQUEST_TIMEOUT,
        )
        if response.ok:
            return response.json().get("email", "")
    except requests.RequestException:
        logger.warning("Failed to fetch Google account email", exc_info=True)
    return ""


class GoogleCalendarProvider(CalendarProvider):
    """Reads busy intervals from a user's primary Google calendar."""

    @staticmethod
    def webhooks_enabled() -> bool:
        """Whether push-notification channels should be registered."""
        return bool(getattr(settings, "GOOGLE_CALENDAR_WEBHOOK_ENABLED", False)) and (
            is_configured()
        )

    def _access_token(self) -> str:
        """Return a valid access token, refreshing it if necessary."""
        connection = self.connection
        expiry = connection.token_expiry
        if (
            connection.access_token
            and expiry
            and expiry - TOKEN_EXPIRY_SKEW > timezone.now()
        ):
            return connection.access_token
        return self._refresh_access_token()

    def _refresh_access_token(self) -> str:
        connection = self.connection
        if not connection.refresh_token:
            raise CalendarSyncError(
                "No refresh token available; the calendar must be reconnected."
            )
        response = _session().post(
            TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": connection.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=REQUEST_TIMEOUT,
        )
        if not response.ok:
            raise CalendarSyncError(
                f"Google token refresh failed ({response.status_code})."
            )
        payload = response.json()
        connection.access_token = payload["access_token"]
        connection.token_expiry = timezone.now() + timedelta(
            seconds=int(payload.get("expires_in", 3600))
        )
        connection.save(update_fields=["access_token", "token_expiry", "updated_at"])
        return connection.access_token

    def get_busy_intervals(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        response = _session().post(
            FREEBUSY_URL,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            json={
                "timeMin": start.astimezone(dt_timezone.utc).isoformat(),
                "timeMax": end.astimezone(dt_timezone.utc).isoformat(),
                "items": [{"id": "primary"}],
            },
            timeout=REQUEST_TIMEOUT,
        )
        if not response.ok:
            raise CalendarSyncError(
                f"Google free/busy query failed ({response.status_code})."
            )
        calendars = response.json().get("calendars", {})
        primary = calendars.get("primary", {})
        if primary.get("errors"):
            raise CalendarSyncError(f"Google free/busy error: {primary['errors']}")

        intervals: list[tuple[datetime, datetime]] = []
        for period in primary.get("busy", []):
            intervals.append((_parse_dt(period["start"]), _parse_dt(period["end"])))
        return intervals

    def watch_events(
        self, channel_id: str, address: str, token: str, ttl_seconds: int
    ) -> dict:
        """Register a push-notification channel on the primary calendar's events.

        ``address`` must be a publicly reachable, domain-verified HTTPS URL.
        Returns ``{"resource_id": str, "expiration": datetime}``.
        """
        expiration_ms = int(
            (timezone.now() + timedelta(seconds=ttl_seconds)).timestamp() * 1000
        )
        response = _session().post(
            EVENTS_WATCH_URL,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            json={
                "id": channel_id,
                "type": "web_hook",
                "address": address,
                "token": token,
                "expiration": str(expiration_ms),
            },
            timeout=REQUEST_TIMEOUT,
        )
        if not response.ok:
            raise CalendarSyncError(
                f"Google events.watch failed ({response.status_code})."
            )
        payload = response.json()
        expiration = payload.get("expiration")
        return {
            "resource_id": payload.get("resourceId", ""),
            "expiration": (
                datetime.fromtimestamp(int(expiration) / 1000, tz=dt_timezone.utc)
                if expiration
                else None
            ),
        }

    def stop_channel(self, channel_id: str, resource_id: str) -> None:
        """Stop a push-notification channel (best-effort)."""
        response = _session().post(
            CHANNELS_STOP_URL,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            json={"id": channel_id, "resourceId": resource_id},
            timeout=REQUEST_TIMEOUT,
        )
        if not response.ok:
            raise CalendarSyncError(
                f"Google channels.stop failed ({response.status_code})."
            )


def _parse_dt(value: str) -> datetime:
    """Parse an RFC 3339 timestamp (e.g. ``2026-07-10T14:00:00Z``) to aware UTC."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        dt_timezone.utc
    )
