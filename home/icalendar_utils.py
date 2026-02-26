"""Utilities for generating iCalendar (.ics) files for events."""

from datetime import datetime
from datetime import timezone as dt_timezone

from icalendar import Calendar
from icalendar import Event as CalEvent


def generate_icalendar(event) -> bytes:
    """Generate an iCalendar (.ics) file for a given event.

    Args:
        event: An Event model instance with start_time, end_time, title,
               location, description, and get_full_url() method.

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
    cal_event.add("location", event.location)
    cal_event.add("url", event.get_full_url())
    if event.description:
        cal_event.add("description", event.description)

    cal.add_component(cal_event)
    return cal.to_ical()
