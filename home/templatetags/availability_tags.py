"""Template tags for availability display."""

from django import template
from django.urls import reverse

from availability.formatting import format_slots_as_ranges

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


@register.filter
def admin_unavailable_url(unavailable_member_ids):
    """
    Build a SessionMembership admin changelist URL filtered to the given user IDs.

    Returns None when there are no ids so templates can fall back to other messaging.
    """
    if not unavailable_member_ids:
        return None
    ids_str = ",".join(str(user_id) for user_id in unavailable_member_ids)
    return (
        reverse("admin:home_sessionmembership_changelist") + f"?user_id__in={ids_str}"
    )
