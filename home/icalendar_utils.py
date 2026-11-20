"""Utilities for generating iCalendar (.ics) files for events."""

from datetime import datetime
from datetime import timezone as dt_timezone

from django.conf import settings
from icalendar import Calendar
from icalendar import Event as CalEvent
from icalendar import vCalAddress


def _description(event) -> str:
    """Build the VEVENT description with the Zoom join link first.

    The event description is shared with the Discord scheduled event, so it
    often points people at Discord. Leading with the Zoom link keeps the
    calendar entry sending people straight to the meeting.
    """
    parts = []
    if event.zoom_link:
        parts.append(f"Join Zoom meeting: {event.zoom_link}")
    if event.description:
        parts.append(event.description)
    if event.is_published:
        parts.append(f"Event details: {event.get_full_url()}")
    return "\n\n".join(parts)


def generate_icalendar(event) -> bytes:
    """Generate an iCalendar (.ics) meeting invite for a given event.

    It's sent as a meeting request (METHOD:REQUEST) so that when the event
    changes, a new invite with the same UID and a higher SEQUENCE moves the
    existing calendar entry instead of adding a second one. Invites are BCC'd,
    so the only attendee listed is the sessions inbox; real recipients can't
    be named without exposing everyone's address. Replies from the apps that
    let recipients RSVP go to the organizer, sessions@.

    Calendar clients that render the URL property as the clickable link
    (e.g. Apple Calendar) get the Zoom join link when one is set, falling
    back to the event page only when it's published on the website.

    Args:
        event: An Event model instance

    Returns:
        Bytes of the .ics file content.
    """
    cal = Calendar()
    cal.add("prodid", "-//Djangonaut Space//djangonaut.space//")
    cal.add("version", "2.0")
    cal.add("method", "REQUEST")

    mailbox = f"mailto:{settings.SESSIONS_FROM_EMAIL}"
    organizer = vCalAddress(mailbox)
    organizer.params["cn"] = "Djangonaut Space"
    attendee = vCalAddress(mailbox)

    cal_event = CalEvent()
    cal_event.add("uid", f"event-{event.pk}@djangonaut.space")
    cal_event.add("sequence", event.calendar_sequence)
    cal_event.add("dtstamp", datetime.now(tz=dt_timezone.utc))
    cal_event.add("organizer", organizer)
    cal_event.add("attendee", attendee)
    cal_event.add("summary", event.title)
    cal_event.add("dtstart", event.start_time)
    cal_event.add("dtend", event.end_time)
    if event.zoom_link:
        cal_event.add("location", event.zoom_link)
    if event.zoom_link:
        cal_event.add("url", event.zoom_link)
    elif event.is_published:
        cal_event.add("url", event.get_full_url())
    if description := _description(event):
        cal_event.add("description", description)

    cal.add_component(cal_event)
    return cal.to_ical()
