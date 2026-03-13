import logging

from django.conf import settings
from django.db import transaction
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

    with transaction.atomic():
        #  not really  sure whether using a get_object_or_404 here would be appropriate than
        # a try except
        try:
            event = Event.objects.select_for_update().get(pk=event_id)
        except Event.DoesNotExist:
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

        event.video_link = join_url
        event.save(update_fields=["video_link"])

    logger.info("Zoom meeting created for event %s", event_id)
