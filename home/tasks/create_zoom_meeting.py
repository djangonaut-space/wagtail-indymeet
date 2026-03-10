import logging

from django.conf import settings
from django_tasks import task
from home.models import Event
from home.integrations.zoom.service import create_event_meeting

logger = logging.getLogger(__name__)


def zoom_enabled() -> bool:
    """Check whether Zoom integration is configured."""
    return all(
        [
            getattr(settings, "ZOOM_ACCOUNT_ID", ""),
            getattr(settings, "ZOOM_CLIENT_ID", ""),
            getattr(settings, "ZOOM_CLIENT_SECRET", ""),
        ]
    )


@task()
def create_zoom_meeting(event_id: int) -> None:
    """
    Create a Zoom meeting for an event and store the join URL.

    Safely handles:
    - missing credentials
    - deleted events
    - concurrent updates
    """

    if not zoom_enabled():
        logger.warning(
            "Zoom credentials not configured; skipping meeting creation for event %s",
            event_id,
        )
        return

    event = Event.objects.filter(pk=event_id).first()

    if not event:
        logger.warning("Event %s no longer exists", event_id)
        return

    if event.video_link:
        # Already set (maybe manually)
        return

    try:
        join_url = create_event_meeting(event)

    except Exception:
        logger.exception(
            "Failed to create Zoom meeting for event %s",
            event_id,
        )
        return

    # Avoid overwriting if already set
    updated = Event.objects.filter(
        pk=event_id,
        video_link="",
    ).update(video_link=join_url)

    if updated:
        logger.info("Zoom meeting created for event %s", event_id)
