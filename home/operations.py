import enum
import logging
from typing import NamedTuple

from home.integrations.zoom.service import zoom_enabled
from home.models import Event
from home.tasks.sync_event import sync_event

logger = logging.getLogger(__name__)


class EventSyncStatus(enum.Enum):
    QUEUED = "queued"
    SKIPPED_NO_ZOOM_CONFIGURED = "skipped_no_zoom_configured"


class EventSyncDecision(NamedTuple):
    status: EventSyncStatus
    message: str


def dispatch_event_sync(event: Event) -> EventSyncDecision:
    """Decide whether an event needs external syncing and enqueue the task.

    Called from ``EventAdmin.save_model`` after the event is saved, and from
    the "Resync to Zoom and Discord" admin action. Returns a decision the
    admin maps to a user-facing message. No Zoom link and Zoom not configured
    will be logged for maintainers.
    """
    has_external_state = bool(
        event.zoom_link or event.zoom_meeting_id or event.discord_event_id
    )
    if has_external_state or zoom_enabled():
        sync_event.enqueue(event_id=event.pk)
        return EventSyncDecision(
            EventSyncStatus.QUEUED,
            "Syncing this event to Zoom and Discord in the background.",
        )

    logger.warning(
        "Event %s has no Zoom link and Zoom is not configured; "
        "no Zoom or Discord sync was queued.",
        event.pk,
    )
    return EventSyncDecision(
        EventSyncStatus.SKIPPED_NO_ZOOM_CONFIGURED,
        "This event has no Zoom link and Zoom isn't configured, so no Discord "
        "event was created. Add a Zoom link to the event to enable Discord sync.",
    )
