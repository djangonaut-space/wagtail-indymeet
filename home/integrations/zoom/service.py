import logging
from typing import NamedTuple

from django.conf import settings

from home.integrations.zoom.client import ZoomClient

logger = logging.getLogger(__name__)

zoom_client = ZoomClient()


class ZoomMeeting(NamedTuple):
    """The fields we keep from a created Zoom meeting."""

    join_url: str
    meeting_id: str


def zoom_enabled() -> bool:
    """Check whether Zoom integration is configured."""
    return all(
        [
            getattr(settings, "ZOOM_ACCOUNT_ID", ""),
            getattr(settings, "ZOOM_CLIENT_ID", ""),
            getattr(settings, "ZOOM_CLIENT_SECRET", ""),
        ]
    )


def _duration_minutes(event) -> int:
    return max(1, int((event.end_time - event.start_time).total_seconds() / 60))


def create_event_meeting(event) -> ZoomMeeting:
    """Create a Zoom meeting for an Event and return its join URL and meeting ID."""
    meeting = zoom_client.create_meeting(
        topic=event.title,
        start_time=event.start_time,
        duration_minutes=_duration_minutes(event),
    )
    return ZoomMeeting(join_url=meeting["join_url"], meeting_id=str(meeting["id"]))


def update_event_meeting(event) -> None:
    """Update the Zoom meeting to match the event's current title, time, and duration."""
    zoom_client.patch_meeting(
        meeting_id=event.zoom_meeting_id,
        topic=event.title,
        start_time=event.start_time,
        duration_minutes=_duration_minutes(event),
    )
