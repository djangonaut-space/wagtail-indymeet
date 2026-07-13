"""High-level calendar busy-time helpers used by views and background tasks.

Busy times are cached in the database (``CalendarBusyPeriod``) so reads never
touch the external API. The cache is refreshed out-of-band via three paths that
all funnel through :func:`sync_connection`: webhooks (Google push notifications,
when enabled), polling (the ``sync_calendars`` command), and lazy refresh
(reading stale data enqueues a background re-sync).
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from availability.models import CalendarBusyPeriod, CalendarConnection
from availability.providers import google
from availability.providers.base import CalendarProvider, CalendarSyncError
from availability.slots import current_week_window, intervals_to_slots

logger = logging.getLogger(__name__)

# How far ahead to cache busy periods.
SYNC_HORIZON = timedelta(days=30)
# Busy periods ending more than this far in the past are pruned.
RETENTION = timedelta(days=7)
# A connection is stale (eligible for refresh) once its last sync is older than this.
SYNC_STALE_AFTER = timedelta(hours=6)
# Renew the webhook channel once it is within this window of expiring.
CHANNEL_RENEW_BEFORE = timedelta(days=1)
# Requested webhook channel lifetime; Google clamps to its max.
WATCH_TTL_SECONDS = 7 * 24 * 60 * 60


def get_provider(connection: CalendarConnection) -> CalendarProvider:
    """Instantiate the provider implementation for a connection."""
    return google.GoogleCalendarProvider(connection)


def webhooks_enabled() -> bool:
    """Whether push-notification channels should be registered."""
    return bool(getattr(settings, "GOOGLE_CALENDAR_WEBHOOK_ENABLED", False)) and (
        google.is_configured()
    )


def _webhook_address() -> str:
    """Absolute URL Google POSTs push notifications to."""
    return settings.BASE_URL + reverse("google_calendar_webhook")


def _ensure_webhook_channel(
    connection: CalendarConnection, provider: CalendarProvider, now: datetime
) -> None:
    """Register or renew the connection's push-notification channel.

    No-op when webhooks are disabled or the current channel is still valid. A
    failure here is not fatal to a sync -- the caller falls back to polling.
    """
    if not webhooks_enabled():
        return
    if (
        connection.webhook_channel_id
        and connection.webhook_expires_at
        and connection.webhook_expires_at - CHANNEL_RENEW_BEFORE > now
    ):
        return

    if connection.webhook_channel_id and connection.webhook_resource_id:
        try:
            provider.stop_channel(
                connection.webhook_channel_id, connection.webhook_resource_id
            )
        except CalendarSyncError:
            logger.warning(
                "Failed to stop expiring calendar channel for connection %s",
                connection.pk,
                exc_info=True,
            )

    channel_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    result = provider.watch_events(
        channel_id, _webhook_address(), token, WATCH_TTL_SECONDS
    )
    connection.webhook_channel_id = channel_id
    connection.webhook_channel_token = token
    connection.webhook_resource_id = result["resource_id"]
    connection.webhook_expires_at = result["expiration"]


def sync_connection(
    connection: CalendarConnection, now: datetime | None = None
) -> None:
    """Refresh a connection's cached busy periods from the provider.

    Fetches the next :data:`SYNC_HORIZON` of busy intervals, replaces the stored
    future periods, prunes old ones, (re)registers the webhook channel when
    enabled, and records sync metadata. Raises :class:`CalendarSyncError` if the
    busy-time fetch fails (existing periods are left untouched in that case).
    """
    now = now or timezone.now()
    window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = now + SYNC_HORIZON
    provider = get_provider(connection)

    connection.last_sync_attempted_at = now
    try:
        intervals = provider.get_busy_intervals(window_start, window_end)
    except CalendarSyncError as exc:
        connection.last_sync_error = str(exc)
        connection.save(
            update_fields=["last_sync_attempted_at", "last_sync_error", "updated_at"]
        )
        raise

    with transaction.atomic():
        connection.busy_periods.ending_after(window_start).delete()
        CalendarBusyPeriod.objects.bulk_create(
            [
                CalendarBusyPeriod(connection=connection, start=start, end=end)
                for start, end in intervals
            ]
        )
        connection.busy_periods.ending_before(now - RETENTION).delete()

    try:
        _ensure_webhook_channel(connection, provider, now)
    except CalendarSyncError:
        logger.warning(
            "Webhook channel registration failed for connection %s; "
            "relying on polling/lazy refresh",
            connection.pk,
            exc_info=True,
        )

    connection.last_synced_at = now
    connection.synced_until = window_end
    connection.last_sync_error = ""
    connection.save(
        update_fields=[
            "last_synced_at",
            "last_sync_attempted_at",
            "synced_until",
            "last_sync_error",
            "webhook_channel_id",
            "webhook_channel_token",
            "webhook_resource_id",
            "webhook_expires_at",
            "updated_at",
        ]
    )


def connection_busy_slots(
    connection: CalendarConnection, now: datetime | None = None
) -> set[float]:
    """Busy recurring-week slots for a single connection (current week, from today).

    Reads only from the cached ``CalendarBusyPeriod`` rows -- no external call.
    """
    window_start, window_end, week_start = current_week_window(now)
    periods = connection.busy_periods.overlapping(window_start, window_end)
    intervals = [(period.start, period.end) for period in periods]
    return intervals_to_slots(intervals, week_start, window_start)


def users_busy_slots(users, now: datetime | None = None) -> dict[int, set[float]]:
    """Union of cached busy slots across all connections, for many users in one query."""
    window_start, window_end, week_start = current_week_window(now)
    busy_by_user: dict[int, set[float]] = {user.id: set() for user in users}

    intervals_by_user: dict[int, list[tuple[datetime, datetime]]] = {}
    periods = (
        CalendarBusyPeriod.objects.for_users(users)
        .overlapping(window_start, window_end)
        .values_list("connection__user_id", "start", "end")
    )
    for user_id, start, end in periods:
        intervals_by_user.setdefault(user_id, []).append((start, end))

    for user_id, intervals in intervals_by_user.items():
        busy_by_user[user_id] = intervals_to_slots(intervals, week_start, window_start)

    return busy_by_user


def effective_slots(saved_slots, busy_slots: set[float]) -> list[float]:
    """Saved availability minus busy slots, sorted."""
    return sorted(set(saved_slots) - busy_slots)


def prune_busy_periods(now: datetime | None = None) -> int:
    """Delete cached busy periods ending more than :data:`RETENTION` ago."""
    now = now or timezone.now()
    deleted, _ = CalendarBusyPeriod.objects.ending_before(now - RETENTION).delete()
    return deleted


def stale_connections(user, now: datetime | None = None) -> list[CalendarConnection]:
    """Connections whose cached data is missing or older than :data:`SYNC_STALE_AFTER`."""
    now = now or timezone.now()
    return list(user.calendar_connections.stale(now - SYNC_STALE_AFTER))


def stale_connections_bulk(
    users, now: datetime | None = None
) -> list[CalendarConnection]:
    """Stale connections across many users in a single query."""
    now = now or timezone.now()
    return list(
        CalendarConnection.objects.for_users(users).stale(now - SYNC_STALE_AFTER)
    )
