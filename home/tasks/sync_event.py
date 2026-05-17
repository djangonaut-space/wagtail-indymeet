import logging

from django.db import transaction
from django.utils import timezone
from django_tasks import task

from home.integrations.discord.service import (
    create_event,
    discord_enabled,
    update_event,
)
from home.integrations.zoom.service import (
    create_event_meeting,
    update_event_meeting,
    zoom_enabled,
)
from home.models import Event

logger = logging.getLogger(__name__)


@task()
def sync_event(event_id: int) -> None:
    """Create or update the Zoom meeting and Discord event for an Event.

    A single task owns both side effects, triggered by
    ``operations.dispatch_event_sync`` from ``EventAdmin.save_model``. Zoom runs
    first because Discord uses the Zoom link as its location, and the link set
    here is visible to the Discord step within the same run. Each integration is
    isolated in its own ``try`` so a failure in one doesn't block the other.
    """
    with transaction.atomic():
        try:
            event = Event.objects.select_for_update().get(pk=event_id)
        except Event.DoesNotExist:
            logger.warning("Event %s no longer exists", event_id)
            return

        changed = False

        if zoom_enabled():
            try:
                if not event.zoom_link and not event.zoom_meeting_id:
                    meeting = create_event_meeting(event)
                    event.zoom_link = meeting.join_url
                    event.zoom_meeting_id = meeting.meeting_id
                    event.zoom_synced_at = timezone.now()
                    changed = True
                elif event.zoom_meeting_id:
                    update_event_meeting(event)
                    event.zoom_synced_at = timezone.now()
                    changed = True
            except Exception:
                logger.exception("Failed to sync Zoom meeting for event %s", event_id)

        if discord_enabled() and event.zoom_link:
            try:
                if not event.discord_event_id:
                    event.discord_event_id = create_event(event)
                    event.discord_synced_at = timezone.now()
                    changed = True
                else:
                    update_event(event)
                    event.discord_synced_at = timezone.now()
                    changed = True
            except Exception:
                logger.exception("Failed to sync Discord event for event %s", event_id)

        if changed:
            event.save()

    logger.info("Event %s synced to external systems", event_id)
