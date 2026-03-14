"""Views for comparing availability across multiple users."""

from dataclasses import asdict, dataclass
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.models import CustomUser
from home.forms import CompareAvailabilityForm
from home.availability import (
    convert_slot_with_offset,
    format_slot_as_time,
    get_user_slots,
    slot_to_datetime,
)
from home.models import Session, SessionMembership

SlotAvailabilities = dict[str, list[int]]


@dataclass
class GridCell:
    """Represents a single cell in the availability grid."""

    slot_key: str
    color: str
    available_count: int
    total_count: int
    display_time: str
    utc_datetime: datetime


@dataclass
class GridRow:
    """Represents a row in the availability grid."""

    time_label: str
    show_time_label: bool
    cells: list[GridCell]


@dataclass
class SelectedUser:
    """Represents a selected user for display and JSON serialization."""

    id: int
    display_name: str


def get_slot_color(available_count: int, total_count: int) -> str | None:
    """
    Calculate the background color for a slot based on availability.

    Full purple (ds-purple) when everyone is available, fading to no color when nobody is.
    """
    if total_count == 0 or available_count == 0:
        return None
    if available_count == total_count:
        return "rgba(92, 2, 135, 1.0)"
    # Limit the max opacity of any fractional amount to 70%
    # This will create a bigger visual difference between everyone
    # being able to meet and all but one person being able to meet.
    opacity = (available_count / total_count) * 0.70

    # ds-purple (#5c0287) = rgb(92, 2, 135)
    return f"rgba(92, 2, 135, {opacity})"


def build_grid_data(
    selected_users: list[CustomUser],
    user_slots: dict[int, set[float]],
    offset_hours: float = 0,
) -> tuple[list[GridRow], SlotAvailabilities]:
    """
    Build grid rows and slot availability mapping.

    Returns:
        Tuple of (grid_rows, slot_availabilities) where slot_availabilities
        contains availability data for each slot for Alpine.js
    """
    rows = []
    slot_availabilities: SlotAvailabilities = {}
    total_count = len(selected_users)

    for hour in range(24):
        for half in range(2):
            time_value = hour + (half * 0.5)
            cells = []

            for day in range(7):
                local_slot = (day * 24.0) + time_value
                utc_slot = convert_slot_with_offset(local_slot, -offset_hours)

                available_user_ids = [
                    user.id
                    for user in selected_users
                    if utc_slot in user_slots.get(user.id, set())
                ]

                slot_key = f"{day}-{hour}-{half}"
                slot_availabilities[slot_key] = available_user_ids

                cells.append(
                    GridCell(
                        slot_key=slot_key,
                        color=get_slot_color(len(available_user_ids), total_count),
                        available_count=len(available_user_ids),
                        total_count=total_count,
                        display_time=format_slot_as_time(local_slot),
                        utc_datetime=slot_to_datetime(utc_slot),
                    )
                )

            time_label = f"{hour}:00" if half == 0 else ""
            rows.append(
                GridRow(
                    time_label=time_label,
                    show_time_label=(half == 0),
                    cells=cells,
                )
            )

    return rows, slot_availabilities


@login_required
def compare_availability(request):
    """
    Display a calendar view for comparing availability across multiple users.

    Access is determined by:
    - Session organizers: Can select all session participants
    - Team members (Navigators/Captains/Djangonauts): Can select team members only
    - Users with home.compare_org_availability permission: Can access without session context
    """
    form = CompareAvailabilityForm(data=request.GET, user=request.user)
    if form.is_valid():
        selectable_users = form.get_selectable_users()
        selected_users = form.get_selected_users(selectable_users)
    else:
        selectable_users = []
        selected_users = []

    context = {
        "form": form,
        "selectable_users": selectable_users,
        "selected_user_ids": [u.id for u in selected_users],
        "session_id": form.data.get("session"),
    }
    return render(request, "home/compare_availability.html", context)


@login_required
def compare_availability_grid(request):
    """
    Return the availability grid partial for htmx requests.

    This endpoint is called via htmx to load the grid with the correct
    timezone offset from the client.
    """
    form = CompareAvailabilityForm(data=request.GET, user=request.user)
    if form.is_valid():
        selectable_users = form.get_selectable_users()
        selected_users = form.get_selected_users(selectable_users)
        offset_hours = form.get_offset_hours()

        user_slots = {}
        for user in selected_users:
            slots = get_user_slots(user)
            user_slots[user.id] = set(slots)
    else:
        selected_users = []
        offset_hours = 0.0
        user_slots = {}

    grid_rows, slot_availabilities = build_grid_data(
        selected_users, user_slots, offset_hours
    )
    context = {
        "selected_users": [
            asdict(
                SelectedUser(
                    id=user.id,
                    display_name=user.get_full_name() or user.username,
                )
            )
            for user in selected_users
        ],
        "grid_rows": grid_rows,
        "slot_availabilities": slot_availabilities,
    }
    return render(request, "home/_compare_availability_grid.html", context)
