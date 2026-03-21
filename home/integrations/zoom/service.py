import logging

from home.integrations.zoom.client import ZoomClient

logger = logging.getLogger(__name__)

zoom_client = ZoomClient()


def create_event_meeting(event) -> str:
    """
    Create a Zoom meeting for an Event.

    Returns:
        join_url (str)
    """

    duration_minutes = max(
        1,
        int((event.end_time - event.start_time).total_seconds() / 60),
    )

    meeting = zoom_client.create_meeting(
        topic=event.title,
        start_time=event.start_time,
        duration_minutes=duration_minutes,
    )

    return meeting["join_url"]
