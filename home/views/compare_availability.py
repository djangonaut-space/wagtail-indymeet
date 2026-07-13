"""Views for comparing availability across multiple users."""

from dataclasses import asdict, dataclass
from datetime import datetime

from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.models import CustomUser
from availability.providers.service import users_busy_slots
from availability.tasks import refresh_stale_connections_bulk
from home.availability import (
    convert_slot_with_offset,
    format_slot_as_time,
    get_user_slots,
    slot_to_datetime,
)
from home.models import Session, SessionMembership
from home.widgets import TomSelectMultipleWidget

slotAvailabilities = dict[str, list[int]]


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
) -> tuple[list[GridRow], slotAvailabilities]:
    """
    Build grid rows and slot availability mapping.

    Returns:
        Tuple of (grid_rows, slot_availabilities) where slot_availabilities
        contains availability data for each slot for Alpine.js
    """
    rows = []
    slot_availabilities: slotAvailabilities = {}
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


class CompareAvailabilityForm(forms.Form):
    """
    Form for handling compare availability querystring parameters.

    Validates session_id, user selection, and offset parameters.
    Also determines which users the current user can select for comparison.
    """

    session = forms.ModelChoiceField(
        queryset=Session.objects.all(),
        required=False,
    )
    users = forms.MultipleChoiceField(
        choices=[],
        required=False,
        widget=TomSelectMultipleWidget(),
    )
    offset = forms.FloatField(required=False, initial=0)
    include_calendars = forms.BooleanField(required=False, initial=False)

    def __init__(self, data=None, *args, user: CustomUser, **kwargs):
        """
        Initialize form with the requesting user.

        Selectable users are computed eagerly so the widget has choices at render time.
        The session is resolved from the raw data (before validation) because
        available user choices depend on it.

        Args:
            user: The currently logged-in user making the request
        """
        super().__init__(data, *args, **kwargs)
        self.user = user
        session = None
        session_membership = None
        if session_id := (data and data.get("session")):
            session_membership = (
                SessionMembership.objects.for_user(user)
                .filter(session_id=session_id)
                .select_related("session")
                .first()
            )
            if session_membership:
                session = session_membership.session
            else:
                session = Session.objects.filter(pk=session_id).first()

        self._selectable_users: list[CustomUser] = list(
            CustomUser.objects.for_comparing_availability(
                user=user,
                session=session,
                session_membership=session_membership,
            )
        )
        self.fields["users"].choices = [
            (str(u.id), u.get_full_name() or u.username) for u in self._selectable_users
        ]

    def clean_offset(self) -> float:
        """Return offset value, defaulting to 0 if not provided or invalid."""
        offset = self.cleaned_data.get("offset")
        return offset if offset is not None else 0.0

    def clean_users(self) -> set[int]:
        """Convert validated choice strings to a set of integer user IDs."""
        return {int(v) for v in self.cleaned_data.get("users", [])}

    def get_selectable_users(self) -> list[CustomUser]:
        """
        Get users that the current user can select for comparison.

        Returns:
            List of CustomUser objects the user can compare
        """
        return self._selectable_users

    def get_selected_users(
        self, selectable_users: list[CustomUser]
    ) -> list[CustomUser]:
        """
        Get the users that are currently selected from the selectable users.

        Args:
            selectable_users: List of users that can be selected

        Returns:
            List of selected CustomUser objects
        """
        if not self.cleaned_data["users"]:
            return []
        return [u for u in selectable_users if u.id in self.cleaned_data["users"]]

    def get_offset_hours(self) -> float:
        """Return the validated offset hours value."""
        return self.cleaned_data.get("offset", 0)

    def get_user_slots_map(
        self, selected_users: list[CustomUser]
    ) -> dict[int, set[float]]:
        """
        Build a mapping of user id to available slots for the selected users.

        Fetches saved availability and, when requested, calendar busy times in
        bulk (a constant number of queries regardless of user count).
        """
        user_slots = {user.id: set(get_user_slots(user)) for user in selected_users}
        if not selected_users:
            return user_slots

        if self.cleaned_data.get("include_calendars", False):
            # Subtract this week's busy times so the overlap reflects real conflicts.
            busy_slots_by_user = users_busy_slots(selected_users)
            for user in selected_users:
                user_slots[user.id] -= busy_slots_by_user.get(user.id, set())
            # Reads serve cached data; refresh stale connections in the background.
            refresh_stale_connections_bulk(selected_users)

        return user_slots


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
        selected_user_ids = form.cleaned_data.get("users", [])
    else:
        selected_user_ids = []
    context = {
        "form": form,
        "selected_user_ids": selected_user_ids,
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
        user_slots = form.get_user_slots_map(selected_users)
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
