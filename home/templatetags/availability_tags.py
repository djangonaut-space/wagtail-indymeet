"""Template tags for availability display."""

from django import template

from home.availability import format_slots_as_ranges

register = template.Library()


@register.simple_tag
def format_slots_as_list(slots, timezone_name="UTC"):
    """
    Format availability slots as a list of time ranges.

    Args:
        slots: List of UTC reference availability slot values
        timezone_name: IANA timezone name for display conversion

    Returns:
        List of formatted time range strings
    """
    if not slots:
        return []
    return format_slots_as_ranges(slots, timezone_name or "UTC")
