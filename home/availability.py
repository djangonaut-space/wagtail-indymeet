"""
Utility functions for calculating availability overlaps between users.

These functions are used primarily for team formation, where we need to ensure
that navigators can meet with all team members simultaneously, and captains
can meet with each djangonaut individually.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.urls import reverse

from accounts.models import UserAvailability
from home.models import Team, Session, SessionMembership

if TYPE_CHECKING:
    from accounts.models import CustomUser

# Constants for availability calculations
SLOT_INCREMENT = 0.5  # Each slot represents 30 minutes
FLOAT_COMPARISON_THRESHOLD = 0.01  # Threshold for float equality checks
HOURS_PER_WEEK = 168  # Total hours in a week (7 days * 24 hours)


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

    slot_range: tuple[float, float]
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

        Uses a reference date (next Sunday from today) to create an actual
        datetime that can be used with templatetags like time_is_link.

        Returns:
            UTC datetime for the start of this availability window
        """
        return slot_to_datetime(self.slot_range[0])


def slot_to_datetime(slot: float) -> datetime:
    """
    Convert a slot value to a datetime using the next Sunday as a reference date.

    This creates a concrete datetime that can be used with templatetags like
    time_is_link. The date is arbitrary (next Sunday from today) since
    availability is weekly and recurring.

    Args:
        slot: Time slot value (0.0 = Sunday 00:00, 167.5 = Saturday 23:30)

    Returns:
        A datetime for the given slot, anchored to the upcoming week
    """
    today = datetime.now().date()
    days_until_sunday = (6 - today.weekday()) % 7
    if days_until_sunday == 0:
        days_until_sunday = 7
    next_sunday = today + timedelta(days=days_until_sunday)

    day_offset = int(slot // 24)
    hour_in_day = slot % 24
    hours = int(hour_in_day)
    minutes = int((hour_in_day % 1) * 60)

    target_date = next_sunday + timedelta(days=day_offset)
    return datetime.combine(target_date, datetime.min.time()).replace(
        hour=hours, minute=minutes
    )


def _convert_to_12hour_format(hour_24: int) -> tuple[int, str]:
    """
    Convert 24-hour format to 12-hour format with AM/PM.

    Args:
        hour_24: Hour in 24-hour format (0-23)

    Returns:
        Tuple of (hour_12, period) where hour_12 is 1-12 and period is "AM" or "PM"
    """
    period = "AM" if hour_24 < 12 else "PM"
    hour_12 = hour_24 % 12
    if hour_12 == 0:
        hour_12 = 12
    return hour_12, period


def _group_consecutive_slots(sorted_slots: list[float]) -> list[tuple[float, float]]:
    """
    Group consecutive time slots into ranges.

    Args:
        sorted_slots: Sorted list of time slot values

    Returns:
        List of (range_start, range_end) tuples representing consecutive slot ranges
    """
    if not sorted_slots:
        return []

    ranges = []
    range_start = sorted_slots[0]
    range_end = sorted_slots[0]

    for i in range(1, len(sorted_slots)):
        # Check if consecutive (SLOT_INCREMENT apart)
        if (
            abs(sorted_slots[i] - range_end - SLOT_INCREMENT)
            < FLOAT_COMPARISON_THRESHOLD
        ):
            range_end = sorted_slots[i]
        else:
            # End current range and start new one
            ranges.append((range_start, range_end))
            range_start = sorted_slots[i]
            range_end = sorted_slots[i]

    # Add final range
    ranges.append((range_start, range_end))

    return ranges


def get_user_slots(user: "CustomUser") -> list[float]:
    """
    Get availability slots for a user.

    Args:
        user: A CustomUser instance

    Returns:
        List of float values representing 30-minute time slots (0.0-167.5)
        Returns empty list if user has no availability set
    """
    try:
        return user.availability.slots if hasattr(user, "availability") else []
    except UserAvailability.DoesNotExist:
        return []


def get_role_slots(team: Team, role) -> list[float]:
    """
    Get all unique availability slots from users with a given role on a team.

    Args:
        team: The team to get navigator slots from
        role: The membership role to get slots from

    Returns:
        Sorted list of unique slot values from all users with the role (always as floats)
    """
    members = (
        team.session_memberships.filter(role=role)
        .select_related("user")
        .prefetch_related("user__availability")
    )

    all_slots = set()
    for member in members:
        user_slots = get_user_slots(member.user)
        # Ensure all slots are floats to avoid mixed type arrays
        all_slots.update(float(slot) for slot in user_slots)

    return sorted(all_slots)


def count_one_hour_blocks(slots: list[float]) -> int:
    """
    Count the number of 1-hour blocks from a list of 30-minute slots.

    A 1-hour block consists of two consecutive 30-minute slots.
    For example: [1.0, 1.5] counts as 1 hour, [2.0, 2.5, 3.0] counts as 2 hours.

    Args:
        slots: Sorted list of time slot values (in 0.5 increments)

    Returns:
        Number of complete 1-hour blocks
    """
    if not slots:
        return 0

    hour_blocks = 0
    i = 0

    while i < len(slots) - 1:
        # Check if current slot and next slot are consecutive
        if abs(slots[i + 1] - slots[i] - SLOT_INCREMENT) < FLOAT_COMPARISON_THRESHOLD:
            hour_blocks += 1
            i += 2  # Skip both slots that form this hour block
        else:
            i += 1  # Move to next slot

    return hour_blocks


def calculate_overlap(users: list["CustomUser"]) -> tuple[list[float], int]:
    """
    Find time slots where ALL users in a list are available simultaneously.

    Args:
        users: List of CustomUser instances

    Returns:
        Tuple of (overlapping_slots, hour_blocks_count)
        - overlapping_slots: Sorted list of time slot values where ALL users overlap
        - hour_blocks_count: Number of complete 1-hour blocks
    """
    if not users:
        return [], 0

    # Get all users' slots
    all_user_slots = [set(get_user_slots(user)) for user in users]

    # Find intersection of all users' availability
    overlapping_slots = set.intersection(*all_user_slots)
    sorted_overlap = sorted(overlapping_slots)

    # Count 1-hour blocks
    hour_blocks = count_one_hour_blocks(sorted_overlap)

    return sorted_overlap, hour_blocks


def calculate_team_overlap(
    navigator_users: list["CustomUser"],
    captain_user: "CustomUser | None",
    djangonaut_users: list["CustomUser"],
) -> dict[str, int | list[float] | list[dict] | bool]:
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
        - navigator_meeting_slots: List of overlapping time slots for navigator meetings
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

    # Calculate navigator meeting overlap (navigators + djangonauts, no captain)
    navigator_meeting_participants = navigator_users + djangonaut_users
    if navigator_meeting_participants:
        nav_slots, nav_hours = calculate_overlap(navigator_meeting_participants)
        result["navigator_meeting_slots"] = nav_slots
        result["navigator_meeting_hours"] = nav_hours
        result["is_valid"] = nav_hours >= Team.MIN_NAVIGATOR_MEETING_HOURS

    # Calculate captain 1-on-1 overlaps with each djangonaut
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

        # Mark team as invalid if any djangonaut has insufficient captain overlap
        min_captain_hours = min(
            (meeting["hours"] for meeting in captain_meetings), default=0
        )
        result["min_captain_hours"] = min_captain_hours
        if min_captain_hours < Team.MIN_CAPTAIN_OVERLAP_HOURS:
            result["is_valid"] = False

    return result


def convert_slot_with_offset(slot: float, offset_hours: float) -> float:
    """
    Convert a UTC slot to a different timezone using UTC offset.

    Args:
        slot: UTC slot value (0.0-167.5)
        offset_hours: UTC offset in hours (e.g., -5 for EST, +1 for CET)

    Returns:
        Converted slot value, wrapped to stay within 0-168 range
    """
    converted = slot + offset_hours
    # Wrap around the week (0-HOURS_PER_WEEK)
    if converted < 0:
        converted += HOURS_PER_WEEK
    elif converted >= HOURS_PER_WEEK:
        converted -= HOURS_PER_WEEK
    return converted


def format_slot_as_time(slot: float, offset_hours: float = 0) -> str:
    """
    Format a slot value as a human-readable time string.

    Args:
        slot: Time slot value (0.0 = Sunday 00:00 UTC, 167.5 = Saturday 23:30 UTC)
        offset_hours: UTC offset in hours for timezone conversion

    Returns:
        Formatted string like "Mon 2:30 PM"
    """
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    # Apply offset if provided
    if offset_hours != 0:
        slot = convert_slot_with_offset(slot, offset_hours)

    day_index = int(slot // 24)
    hour_in_day = slot % 24
    hours24 = int(hour_in_day)
    minutes = int((hour_in_day % 1) * 60)

    # Convert to 12-hour format with AM/PM
    hours12, period = _convert_to_12hour_format(hours24)

    day_name = days[day_index] if 0 <= day_index < 7 else "???"

    return f"{day_name} {hours12}:{minutes:02d} {period}"


def format_slots_as_ranges(slots: list[float], offset_hours: float = 0) -> list[str]:
    """
    Format a list of slots as time ranges for display.

    Groups consecutive slots into ranges like "Mon 2:00 PM - 3:30 PM".

    Args:
        slots: Sorted list of time slot values
        offset_hours: UTC offset in hours for timezone conversion

    Returns:
        List of formatted time range strings
    """
    if not slots:
        return []

    # Convert all slots first if offset is provided
    if offset_hours != 0:
        converted_slots = [convert_slot_with_offset(s, offset_hours) for s in slots]
        sorted_slots = sorted(converted_slots)
    else:
        sorted_slots = sorted(slots)

    # Group consecutive slots into ranges
    slot_ranges = _group_consecutive_slots(sorted_slots)

    # Format each range
    # Note: offset_hours=0 because slots are already converted above if needed
    formatted_ranges = []
    for range_start, range_end in slot_ranges:
        start_time = format_slot_as_time(range_start, offset_hours=0)
        # Add SLOT_INCREMENT to get the end time (end of the last 30-min slot)
        end_time = format_slot_as_time(range_end + SLOT_INCREMENT, offset_hours=0)
        # Extract just the time portion from end_time (remove day name)
        end_time_only = end_time.split(" ", 1)[1]
        formatted_ranges.append(f"{start_time} - {end_time_only}")

    return formatted_ranges


def format_availability_by_day(
    slots: list[float], offset_hours: float = 0
) -> dict[str, list[str]]:
    """
    Format availability slots grouped by day with time ranges.

    Args:
        slots: List of time slot values (0.0-167.5)
        offset_hours: UTC offset in hours for timezone conversion

    Returns:
        Dict mapping day names to lists of time ranges
        Example: {"Sun": ["7:30 AM - 10:00 AM"], "Mon": ["9:00 AM - 5:00 PM"]}
    """
    if not slots:
        return {}

    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    # Convert all slots first if offset is provided
    if offset_hours != 0:
        converted_slots = [convert_slot_with_offset(s, offset_hours) for s in slots]
    else:
        converted_slots = slots

    day_slots = {day: [] for day in days}

    # Group slots by day
    for slot in sorted(converted_slots):
        day_index = int(slot // 24)
        if 0 <= day_index < 7:
            day_name = days[day_index]
            day_slots[day_name].append(slot)

    # Convert each day's slots to time ranges
    day_ranges = {}
    for day_name, day_slot_list in day_slots.items():
        if not day_slot_list:
            continue

        sorted_day_slots = sorted(day_slot_list)
        slot_ranges = _group_consecutive_slots(sorted_day_slots)

        ranges = []
        for range_start, range_end in slot_ranges:
            start_hour = range_start % 24
            end_hour = (range_end + SLOT_INCREMENT) % 24
            ranges.append(format_time_range(start_hour, end_hour))

        day_ranges[day_name] = ranges

    return day_ranges


def format_time_range(start_hour: float, end_hour: float) -> str:
    """
    Format a time range from hour values in 12-hour AM/PM format.

    Args:
        start_hour: Starting hour (can include .5 for 30 minutes)
        end_hour: Ending hour

    Returns:
        Formatted string like "7:30 AM - 10:00 AM" or "9:00 AM - 5:00 PM"
    """
    start_h = int(start_hour)
    start_m = int((start_hour % 1) * 60)
    end_h = int(end_hour)
    end_m = int((end_hour % 1) * 60)

    # Convert to 12-hour format with AM/PM
    start_h12, start_period = _convert_to_12hour_format(start_h)
    end_h12, end_period = _convert_to_12hour_format(end_h)

    # Format with minutes
    start_str = f"{start_h12}:{start_m:02d} {start_period}"
    end_str = f"{end_h12}:{end_m:02d} {end_period}"

    return f"{start_str} - {end_str}"


def calculate_user_overlap(user1: "CustomUser", user2: "CustomUser") -> list[float]:
    """
    Calculate overlapping availability slots between two individual users.

    Args:
        user1: First CustomUser instance
        user2: Second CustomUser instance

    Returns:
        Sorted list of time slots where both users are available
    """
    slots, _ = calculate_overlap([user1, user2])
    return slots


def find_best_one_hour_windows(
    users: list["CustomUser"], top_n: int = 5
) -> list[AvailabilityWindow]:
    """
    Find top N one-hour time windows with most user availability.

    Analyzes all possible 1-hour windows (335 total across a week) and returns
    the windows with the most users available, ranked by availability.

    Args:
        users: List of CustomUser instances to analyze
        top_n: Number of top windows to return (default 5)

    Returns:
        List of AvailabilityWindow instances sorted by availability (descending)
    """
    one_hour_windows = {}
    total_possible_windows = int(HOURS_PER_WEEK / SLOT_INCREMENT) - 1

    for i in range(total_possible_windows):
        start_slot = i * SLOT_INCREMENT
        end_slot = start_slot + SLOT_INCREMENT

        available_users = []
        unavailable_users = []

        for user in users:
            user_slots = get_user_slots(user)

            if start_slot in user_slots and end_slot in user_slots:
                available_users.append(user)
            else:
                unavailable_users.append(user)

        if len(available_users) > 1:
            start_time = format_slot_as_time(start_slot)
            end_time = format_slot_as_time(end_slot + SLOT_INCREMENT)
            end_time_only = end_time.split(" ", 1)[1]
            formatted_time = f"{start_time} - {end_time_only}"

            one_hour_windows[(start_slot, end_slot)] = AvailabilityWindow(
                slot_range=(start_slot, end_slot),
                formatted_time=formatted_time,
                available_users=available_users,
                unavailable_users=unavailable_users,
            )

    sorted_windows = sorted(
        one_hour_windows.values(),
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
