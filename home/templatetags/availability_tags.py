"""Template tags for availability display."""

from django import template
from django.urls import reverse

from home.availability import AvailabilityWindow, format_slots_as_ranges

register = template.Library()


@register.simple_tag
def format_slots_as_list(slots, timezone_name="UTC"):
    """
    Format availability slots as a list of time ranges.

    Args:
        slots: List of Slot objects
        timezone_name: IANA timezone name for display conversion

    Returns:
        List of formatted time range strings
    """
    if not slots:
        return []
    return format_slots_as_ranges(slots, timezone_name or "UTC")


@register.simple_tag(takes_context=True)
def unavailable_members_admin_url(context, window: AvailabilityWindow) -> str | None:
    """
    Build the admin changelist URL for reviewing a window's unavailable members.

    Carries over whatever filters or search are already in the current
    request's querystring, so following the link keeps them applied (e.g. a
    session filter, so a member with memberships in more than one session
    isn't shown once per session).
    """
    ids = [str(user.id) for user in window.unavailable_users]
    if not ids:
        return None
    params = context["request"].GET.copy()
    params["user_id__in"] = ",".join(ids)
    return f"{reverse('admin:home_sessionmembership_changelist')}?{params.urlencode()}"
