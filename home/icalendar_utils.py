"""Utilities for generating iCalendar (.ics) files for events."""

from datetime import datetime
from datetime import timezone as dt_timezone

from icalendar import Calendar
from icalendar import Event as CalEvent


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
    """Generate an iCalendar (.ics) file for a given event.

    Calendar clients that render the URL property as the clickable link
    (e.g. Apple Calendar) get the Zoom join link when one is set, falling
    back to the event page only when it's published on the website.

    Args:
        event: An Event model instance with start_time, end_time, title,
               zoom_link, description, is_published, and get_full_url().

    Returns:
        Bytes of the .ics file content.
    """
    cal = Calendar()
    cal.add("prodid", "-//Djangonaut Space//djangonaut.space//")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")

    cal_event = CalEvent()
    cal_event.add("uid", f"event-{event.pk}@djangonaut.space")
    cal_event.add("dtstamp", datetime.now(tz=dt_timezone.utc))
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
