"""
Utility functions for calculating availability overlaps between users.

These functions are used primarily for team formation, where we need to ensure
that navigators can meet with all team members simultaneously, and captains
can meet with each djangonaut individually.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from django.urls import reverse

from accounts.models import UserAvailability
from home.models import Session, SessionMembership, Team
from home.slots import HOURS_PER_WEEK, SLOT_INCREMENT, Slot

if TYPE_CHECKING:
    from accounts.models import CustomUser

# Slot conversion and formatting is the Slot class's job (see home.slots); this
# module only aggregates slots across users.
__all__ = [
    "AvailabilityWindow",
    "Slot",
    "calculate_overlap",
    "calculate_team_overlap",
    "calculate_user_overlap",
    "count_one_hour_blocks",
    "find_best_one_hour_windows",
    "find_best_one_hour_windows_with_roles",
    "format_availability_by_day",
    "format_slots_as_ranges",
    "get_role_slots",
    "get_user_slots",
]


@dataclass
class AvailabilityWindow:
    """
    Represents a time window with user availability information.

    Attributes:
        slot_range: Tuple of (start_slot, end_slot) representing the time window
        formatted_time: Human-readable time string (e.g., "Mon 2:00 PM - 3:00 PM")
        available_users: List of users available during this window
        unavailable_users: List of users not available during this window
        role_counts: Optional dict mapping role names to counts
    """

    slot_range: tuple[Slot, Slot]
    formatted_time: str
    available_users: list["CustomUser"]
    unavailable_users: list["CustomUser"]
    role_counts: dict[str, int] = field(default_factory=dict)

    @property
    def total_available(self) -> int:
        """Total count of available users."""
        return len(self.available_users)

    @property
    def role_summary(self) -> str:
        """Format role counts as a comma-separated string."""
        role_parts = [
            f"{role}: {count}" for role, count in self.role_counts.items() if count > 0
        ]
        return ", ".join(role_parts)

    @property
    def unavailable_member_ids(self) -> list[int]:
        return [user.id for user in self.unavailable_users]

    @property
    def admin_unavailable_url(self) -> str | None:
        """Build admin URL for filtering unavailable members."""
        ids = [str(id) for id in self.unavailable_member_ids]
        if not ids:
            return None
        ids_str = ",".join(ids)
        return (
            reverse("admin:home_sessionmembership_changelist")
            + f"?user_id__in={ids_str}"
        )

    @property
    def start_datetime(self) -> datetime:
        """
        Return a datetime object representing the start of this window.

        Returns:
            UTC datetime for the start of this availability window
        """
        return self.slot_range[0].utc


def _group_consecutive_slots(sorted_slots: list[Slot]) -> list[tuple[Slot, Slot]]:
    """
    Group consecutive time slots into ranges.

    Args:
        sorted_slots: Slots sorted chronologically

    Returns:
        List of (range_start, range_end) tuples representing consecutive slot ranges
    """
    if not sorted_slots:
        return []

    ranges = []
    range_start = sorted_slots[0]
    range_end = sorted_slots[0]

    for slot in sorted_slots[1:]:
        if range_end.is_adjacent_to(slot):
            range_end = slot
        else:
            # End current range and start new one
            ranges.append((range_start, range_end))
            range_start = slot
            range_end = slot

    # Add final range
    ranges.append((range_start, range_end))

    return ranges


def get_user_slots(user: "CustomUser") -> list[Slot]:
    """
    Get availability slots for a user, in the user's own timezone.

    Args:
        user: A CustomUser instance

    Returns:
        Slots tagged with the user's ``slots_timezone``. Empty if the user has
        no availability set.
    """
    try:
        availability = user.availability
    except UserAvailability.DoesNotExist:
        return []

    return availability.get_slots()


def get_role_slots(team: Team, role) -> list[Slot]:
    """
    Get all unique availability slots from users with a given role on a team.

    Args:
        team: The team to get navigator slots from
        role: The membership role to get slots from

    Returns:
        Chronologically sorted unique slots from all users with the role
    """
    members = (
        team.session_memberships.filter(role=role)
        .select_related("user")
        .prefetch_related("user__availability")
    )

    all_slots: set[Slot] = set()
    for member in members:
        all_slots.update(get_user_slots(member.user))

    return sorted(all_slots)


def count_one_hour_blocks(slots: list[Slot]) -> int:
    """
    Count the number of 1-hour blocks from a list of 30-minute slots.

    A 1-hour block consists of two consecutive 30-minute slots.

    Args:
        slots: Chronologically sorted slots

    Returns:
        Number of complete 1-hour blocks
    """
    hour_blocks = 0
    i = 0

    while i < len(slots) - 1:
        # Check if current slot and next slot are consecutive
        if slots[i].is_adjacent_to(slots[i + 1]):
            hour_blocks += 1
            i += 2  # Skip both slots that form this hour block
        else:
            i += 1  # Move to next slot

    return hour_blocks


def calculate_overlap(
    users: list["CustomUser"],
) -> tuple[list[Slot], int]:
    """
    Find slots where ALL users are available simultaneously.

    Each user's stored slots are local wall-clock weekly slots in their own
    ``slots_timezone``. Slots compare by instant, so intersecting the users'
    slot sets matches people across timezones without any manual conversion.
    """
    if not users:
        return [], 0

    all_user_slots = [set(get_user_slots(user)) for user in users]

    # Find intersection of all users' availability.
    overlapping_slots = set.intersection(*all_user_slots)
    sorted_overlap = sorted(overlapping_slots)

    # Count 1-hour blocks.
    hour_blocks = count_one_hour_blocks(sorted_overlap)

    return sorted_overlap, hour_blocks


def calculate_team_overlap(
    navigator_users: list["CustomUser"],
    captain_user: "CustomUser | None",
    djangonaut_users: list["CustomUser"],
) -> dict[str, int | list[Slot] | list[dict] | bool]:
    """
    Calculate availability overlaps for an entire team.

    Calculates:
    1. Navigator meeting hours: All navigators + all djangonauts together
    2. Captain 1-on-1 hours: Captain with each individual djangonaut

    Args:
        navigator_users: List of navigator CustomUser instances
        captain_user: Captain CustomUser instance (can be None)
        djangonaut_users: List of djangonaut CustomUser instances

    Returns:
        Dictionary with:
        - navigator_meeting_slots: Slots for navigator meetings
        - navigator_meeting_hours: Number of 1-hour blocks for navigator meetings
        - captain_meetings: List of dicts with djangonaut info and overlap data
        - is_valid: Boolean indicating if team meets minimum requirements (5 hours)
    """
    result = {
        "navigator_meeting_slots": [],
        "navigator_meeting_hours": 0,
        "captain_meetings": [],
        "is_valid": False,
    }

    # Calculate navigator meeting overlap (navigators + djangonauts, no captain).
    navigator_meeting_participants = navigator_users + djangonaut_users
    if navigator_meeting_participants:
        nav_slots, nav_hours = calculate_overlap(navigator_meeting_participants)
        result["navigator_meeting_slots"] = nav_slots
        result["navigator_meeting_hours"] = nav_hours
        result["is_valid"] = nav_hours >= Team.MIN_NAVIGATOR_MEETING_HOURS

    # Calculate captain 1-on-1 overlaps with each djangonaut.
    if captain_user and djangonaut_users:
        captain_meetings = []
        for djangonaut in djangonaut_users:
            slots, hours = calculate_overlap([captain_user, djangonaut])
            captain_meetings.append(
                {
                    "djangonaut": djangonaut,
                    "slots": slots,
                    "hours": hours,
                }
            )
        result["captain_meetings"] = captain_meetings

        # Mark team as invalid if any djangonaut has insufficient captain overlap.
        min_captain_hours = min(
            (meeting["hours"] for meeting in captain_meetings), default=0
        )
        result["min_captain_hours"] = min_captain_hours
        if min_captain_hours < Team.MIN_CAPTAIN_OVERLAP_HOURS:
            result["is_valid"] = False

    return result


def format_slots_as_ranges(
    slots: list[Slot],
    timezone_name: str = "UTC",
) -> list[str]:
    """
    Format slots as time ranges for display.

    Groups consecutive viewer-local slots into ranges like
    "Mon 2:00 PM - 3:30 PM".

    Args:
        slots: Slots to format
        timezone_name: IANA timezone name for display conversion

    Returns:
        List of formatted time range strings
    """
    if not slots:
        return []

    # Re-express in the viewer's timezone so day names and wrap-around read
    # correctly, then group. Slots stay equal to their UTC originals.
    local_slots = sorted(slot.in_tz(timezone_name) for slot in slots)

    formatted_ranges = []
    for range_start, range_end in _group_consecutive_slots(local_slots):
        # Add SLOT_INCREMENT to get the end time (end of the last 30-min slot).
        end_slot = range_end + SLOT_INCREMENT
        formatted_ranges.append(
            f"{range_start.format_local} - {end_slot.format_time_only}"
        )

    return formatted_ranges


def format_availability_by_day(
    slots: list[Slot],
    timezone_name: str = "UTC",
) -> dict[str, list[str]]:
    """
    Format slots grouped by display-local day.

    Args:
        slots: Slots to format
        timezone_name: IANA timezone name for display conversion

    Returns:
        Dict mapping day names to lists of time ranges
        Example: {"Sun": ["7:30 AM - 10:00 AM"], "Mon": ["9:00 AM - 5:00 PM"]}
    """
    if not slots:
        return {}

    local_slots = sorted(slot.in_tz(timezone_name) for slot in slots)

    day_slots: dict[str, list[Slot]] = {day: [] for day in Slot.DAY_NAMES}
    for slot in local_slots:
        if 0 <= slot.day_index < 7:
            day_slots[slot.day_name].append(slot)

    # Convert each day's slots to time ranges.
    day_ranges = {}
    for day_name, day_slot_list in day_slots.items():
        if not day_slot_list:
            continue

        ranges = []
        for range_start, range_end in _group_consecutive_slots(day_slot_list):
            end_slot = range_end + SLOT_INCREMENT
            ranges.append(
                f"{range_start.format_time_only} - {end_slot.format_time_only}"
            )

        day_ranges[day_name] = ranges

    return day_ranges


def calculate_user_overlap(
    user1: "CustomUser",
    user2: "CustomUser",
) -> list[Slot]:
    """
    Calculate overlapping slots between two individual users.

    Args:
        user1: First CustomUser instance
        user2: Second CustomUser instance

    Returns:
        Chronologically sorted slots where both users are available
    """
    slots, _ = calculate_overlap([user1, user2])
    return slots


def find_best_one_hour_windows(
    users: list["CustomUser"],
    top_n: int = 5,
) -> list[AvailabilityWindow]:
    """
    Find top N one-hour UTC windows with most user availability.

    Analyzes all possible 1-hour windows (335 total across a week) and returns
    the windows with the most users available, ranked by availability.

    Args:
        users: List of CustomUser instances to analyze
        top_n: Number of top windows to return (default 5)

    Returns:
        List of AvailabilityWindow instances sorted by availability (descending)
    """
    windows = []
    total_possible_windows = int(HOURS_PER_WEEK / SLOT_INCREMENT) - 1
    user_slots_by_id = {user.id: set(get_user_slots(user)) for user in users}

    for i in range(total_possible_windows):
        start_slot = Slot("UTC", i * SLOT_INCREMENT)
        end_slot = start_slot + SLOT_INCREMENT

        available_users = []
        unavailable_users = []

        for user in users:
            user_slots = user_slots_by_id[user.id]

            if start_slot in user_slots and end_slot in user_slots:
                available_users.append(user)
            else:
                unavailable_users.append(user)

        if len(available_users) > 1:
            window_end = end_slot + SLOT_INCREMENT
            formatted_time = (
                f"{start_slot.format_local} - {window_end.format_time_only}"
            )

            windows.append(
                AvailabilityWindow(
                    slot_range=(start_slot, end_slot),
                    formatted_time=formatted_time,
                    available_users=available_users,
                    unavailable_users=unavailable_users,
                )
            )

    sorted_windows = sorted(
        windows,
        key=lambda x: x.total_available,
        reverse=True,
    )

    return sorted_windows[:top_n]


def find_best_one_hour_windows_with_roles(
    user_roles: dict["CustomUser", str],
    top_n: int = 5,
) -> list[AvailabilityWindow]:
    """
    Find top N one-hour windows with availability and role information.

    This is an extended version of find_best_one_hour_windows that includes
    role-based counting and member ID tracking. Useful for SessionMembership
    or similar use cases where users have roles.

    Args:
        user_roles: Maps each user to their role
        top_n: Number of top windows to return (default 5)

    Returns:
        List of AvailabilityWindow instances with role_counts and
        unavailable_member_ids populated
    """
    windows = find_best_one_hour_windows(list(user_roles.keys()), top_n)

    for window in windows:
        role_counts = {role: 0 for role, _ in SessionMembership.ROLES}

        for user in window.available_users:
            role = user_roles[user]
            role_counts[role] += 1

        window.role_counts = role_counts
    return windows
