"""Template tags for availability display."""

from django import template

from home.availability import format_slots_as_ranges

register = template.Library()


@register.simple_tag
def format_slots_as_list(slots, offset_hours=0):
    """
    Format availability slots as a list of time ranges.

    Args:
        slots: List of availability slot values
        offset_hours: UTC offset in hours for timezone conversion

    Returns:
        List of formatted time range strings
    """
    if not slots:
        return []
    # Ensure offset_hours is a float (template context may pass it as string)
    try:
        offset_hours = float(offset_hours)
    except (ValueError, TypeError):
        offset_hours = 0.0
    return format_slots_as_ranges(slots, offset_hours)
