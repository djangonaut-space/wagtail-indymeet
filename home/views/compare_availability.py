"""Views for comparing availability across multiple users."""

import json
from dataclasses import asdict, dataclass

from django import forms
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from accounts.models import CustomUser
from home.availability import get_user_slots
from home.models import Session, SessionMembership

slotAvailabilities = dict[str, list[int]]


@dataclass
class GridCell:
    """Represents a single cell in the availability grid."""

    slot_key: str
    color: str
    available_count: int
    total_count: int


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
                utc_slot = (day * 24.0) + time_value - offset_hours

                if utc_slot < 0:
                    utc_slot += 168
                elif utc_slot >= 168:
                    utc_slot -= 168

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
    users = forms.CharField(required=False)
    offset = forms.FloatField(required=False, initial=0)

    def __init__(self, *args, user: CustomUser, **kwargs):
        """
        Initialize form with the requesting user.

        Args:
            user: The currently logged-in user making the request
        """
        super().__init__(*args, **kwargs)
        self.user = user
        self._session = None
        self._session_membership = None

    def clean_offset(self) -> float:
        """Return offset value, defaulting to 0 if not provided or invalid."""
        offset = self.cleaned_data.get("offset")
        return offset if offset is not None else 0.0

    def clean_users(self) -> set[int]:
        """Parse user IDs from form data, handling both comma-separated and multiple params."""
        result = set()
        # Handle multiple params (from select multiple) and comma-separated values
        values = (
            self.data.getlist("users")
            if hasattr(self.data, "getlist")
            else [self.data.get("users", "")]
        )
        for value in values:
            for uid in str(value).split(","):
                if uid.strip().isdigit():
                    result.add(int(uid.strip()))
        return result

    def clean_session(self):
        if session := self.cleaned_data.get("session"):
            self._session_membership = (
                SessionMembership.objects.for_session(session)
                .for_user(self.user)
                .first()
            )
        self._session = session
        return self._session

    # TODO move to CustomUserQueryset
    def get_selectable_users(self) -> list[CustomUser]:
        """
        Get users that the current user can select for comparison.

        Builds up a single queryset with appropriate filters based on:
        - Permission: Users with compare_org_availability see all users
        - Organizer role: Can see all session participants
        - Team member: Can see their team members only

        Returns:
            List of CustomUser objects the user can compare

        Raises:
            PermissionDenied: If user lacks permission to compare availability
        """
        users = CustomUser.objects.select_related("profile", "availability").order_by(
            "first_name", "last_name"
        )
        q_filter = Q(availability__isnull=False)
        if self._session:
            q_filter &= Q(session_memberships__session=self._session)
        if (
            self._session_membership
            and self._session_membership.role != SessionMembership.ORGANIZER
        ):
            q_filter &= Q(session_memberships__team=self._session_membership.team)
        # We don't have a session for this user, so let's make sure they can
        # view the whole org's availability.
        elif not self.user.has_perm("home.compare_org_availability"):
            users = users.none()

        return list(users.filter(q_filter).distinct())

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
        offset_hours = form.get_offset_hours()

        user_slots = {}
        for user in selected_users:
            slots = get_user_slots(user)
            user_slots[user.id] = set(slots)
    else:
        selectable_users = []
        selected_users = []
        offset_hours = 0.0
        user_slots = {}

    grid_rows, slot_availabilities = build_grid_data(
        selected_users, user_slots, offset_hours
    )
    context = {
        "form": form,
        "selectable_users": selectable_users,
        "selected_users": [
            asdict(
                SelectedUser(
                    id=user.id,
                    display_name=user.get_full_name() or user.username,
                )
            )
            for user in selected_users
        ],
        "selected_user_ids": [u.id for u in selected_users],
        "grid_rows": grid_rows,
        "slot_availabilities": slot_availabilities,
        "session_id": form.data.get("session"),
        "offset_hours": offset_hours,
    }
    return render(request, "home/compare_availability.html", context)
