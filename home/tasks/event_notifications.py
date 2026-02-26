"""Background tasks for sending event-related notification emails."""

from django_tasks import task

from home import email
from home.icalendar_utils import generate_icalendar
from home.models import Event


@task()
def send_event_calendar_invite(event_id: int, recipients) -> None:
    """Send a calendar invite email with an .ics attachment to recipients.

    The event's extra_emails are always included alongside the primary recipients
    (e.g. sessions@djangonaut.space or guest speakers configured on the event).

    Args:
        event_id: The ID of the Event to send an invite for.
        recipients: A list of email addresses to send the calendar invite to.
    """
    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        return

    ical_data = generate_icalendar(event)
    context = {
        "event": event,
        "cta_link": event.get_full_url(),
    }
    recipients = recipients + list(event.extra_emails or [])
    email.send(
        email_template="event_calendar_invite",
        recipient_list=recipients,
        context=context,
        attachments=[("event.ics", ical_data, "text/calendar")],
    )
