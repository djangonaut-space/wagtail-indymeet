"""Background tasks for sending event-related notification emails."""

from django.utils import timezone
from django_tasks import task

from home import email
from home.icalendar_utils import generate_icalendar
from home.models import Event


@task()
def send_event_calendar_invite(event_id: int) -> None:
    """Send a calendar invite email with an .ics attachment to recipients.

    The event's extra_emails are always included alongside the primary recipients.
    This task is idempotent and will only send invites once.

    Args:
        event_id: The ID of the Event to send an invite for.
    """
    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        return

    if event.calendar_invites_sent_at:
        return

    recipients = event.get_calendar_invite_recipients()
    if not recipients:
        return

    ical_data = generate_icalendar(event)
    context = {
        "event": event,
        "cta_link": event.get_full_url(),
    }

    email.send(
        email_template="event_calendar_invite",
        recipient_list=["sessions@djangonaut.space"],
        bcc_list=recipients,
        context=context,
        attachments=[("event.ics", ical_data, "text/calendar")],
    )
    event.calendar_invites_sent_at = timezone.now()
    event.save(update_fields=["calendar_invites_sent_at"])
