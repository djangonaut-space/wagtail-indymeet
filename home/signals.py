from django.db.models.signals import post_save
from django.dispatch import receiver

from home.models import Event
from home import tasks


@receiver(post_save, sender=Event)
def create_zoom_meeting_on_event_creation(
    sender, instance: Event, created: bool, **kwargs
) -> None:
    """
    Queue Zoom meeting creation when a new event is created.

    Only triggers if the event does not already have a video link.
    """
    if not created or instance.video_link:
        return

    tasks.create_zoom_meeting.enqueue(event_id=instance.pk)
