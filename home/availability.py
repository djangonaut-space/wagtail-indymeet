"""
Utility functions for calculating availability overlaps between users.

These functions are used primarily for team formation, where we need to ensure
that navigators can meet with all team members simultaneously, and captains
can meet with each djangonaut individually.
"""

from typing import Any

from accounts.models import UserAvailability
from home.models import Team


def get_user_slots(user: Any) -> list[float]:
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
        # Check if current slot and next slot are consecutive (0.5 apart)
        if abs(slots[i + 1] - slots[i] - 0.5) < 0.01:  # Float comparison
            hour_blocks += 1
            i += 2  # Skip both slots that form this hour block
        else:
            i += 1  # Move to next slot

    return hour_blocks


def calculate_overlap(users: list[Any]) -> tuple[list[float], int]:
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
    if not all_user_slots:
        return [], 0

    overlapping_slots = set.intersection(*all_user_slots)
    sorted_overlap = sorted(overlapping_slots)

    # Count 1-hour blocks
    hour_blocks = count_one_hour_blocks(sorted_overlap)

    return sorted_overlap, hour_blocks


def calculate_team_overlap(
    navigator_users: list[Any],
    captain_user: Any | None,
    djangonaut_users: list[Any],
) -> dict[str, Any]:
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


def format_slot_as_time(slot: float) -> str:
    """
    Format a slot value as a human-readable time string.

    Args:
        slot: Time slot value (0.0 = Sunday 00:00 UTC, 167.5 = Saturday 23:30 UTC)

    Returns:
        Formatted string like "Mon 14:30"
    """
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    day_index = int(slot // 24)
    hour_in_day = slot % 24
    hours = int(hour_in_day)
    minutes = int((hour_in_day % 1) * 60)

    day_name = days[day_index] if 0 <= day_index < 7 else "???"

    return f"{day_name} {hours:02d}:{minutes:02d}"


def format_slots_as_ranges(slots: list[float]) -> list[str]:
    """
    Format a list of slots as time ranges for display.

    Groups consecutive slots into ranges like "Mon 14:00-15:30".

    Args:
        slots: Sorted list of time slot values

    Returns:
        List of formatted time range strings
    """
    if not slots:
        return []

    sorted_slots = sorted(slots)
    ranges = []
    range_start = sorted_slots[0]
    range_end = sorted_slots[0]

    for i in range(1, len(sorted_slots)):
        # Check if consecutive (0.5 hour apart)
        if abs(sorted_slots[i] - range_end - 0.5) < 0.01:
            range_end = sorted_slots[i]
        else:
            # End current range and start new one
            start_time = format_slot_as_time(range_start)
            end_time = format_slot_as_time(range_end + 0.5)  # Add 30 min to end
            ranges.append(f"{start_time}-{end_time.split()[1]}")  # "Mon 14:00-15:30"
            range_start = sorted_slots[i]
            range_end = sorted_slots[i]

    # Add final range
    start_time = format_slot_as_time(range_start)
    end_time = format_slot_as_time(range_end + 0.5)
    ranges.append(f"{start_time}-{end_time.split()[1]}")

    return ranges


def format_availability_by_day(slots: list[float]) -> dict[str, list[str]]:
    """
    Format availability slots grouped by day with time ranges.

    Args:
        slots: List of time slot values (0.0-167.5)

    Returns:
        Dict mapping day names to lists of time ranges
        Example: {"Sun": ["7:30-10:00", "12:00-13:00"], "Mon": ["9:00-17:00"]}
    """
    if not slots:
        return {}

    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    day_slots = {day: [] for day in days}

    # Group slots by day
    for slot in sorted(slots):
        day_index = int(slot // 24)
        if 0 <= day_index < 7:
            day_name = days[day_index]
            day_slots[day_name].append(slot)

    # Convert each day's slots to time ranges
    day_ranges = {}
    for day_name, day_slot_list in day_slots.items():
        if not day_slot_list:
            continue

        ranges = []
        sorted_day_slots = sorted(day_slot_list)
        range_start = sorted_day_slots[0]
        range_end = sorted_day_slots[0]

        for i in range(1, len(sorted_day_slots)):
            # Check if consecutive (0.5 hour apart)
            if abs(sorted_day_slots[i] - range_end - 0.5) < 0.01:
                range_end = sorted_day_slots[i]
            else:
                # End current range and start new one
                start_hour = range_start % 24
                end_hour = (range_end + 0.5) % 24
                ranges.append(format_time_range(start_hour, end_hour))
                range_start = sorted_day_slots[i]
                range_end = sorted_day_slots[i]

        # Add final range
        start_hour = range_start % 24
        end_hour = (range_end + 0.5) % 24
        ranges.append(format_time_range(start_hour, end_hour))

        day_ranges[day_name] = ranges

    return day_ranges


def format_time_range(start_hour: float, end_hour: float) -> str:
    """
    Format a time range from hour values.

    Args:
        start_hour: Starting hour (can include .5 for 30 minutes)
        end_hour: Ending hour

    Returns:
        Formatted string like "7:30-10:00" or "9-17"
    """
    start_h = int(start_hour)
    start_m = int((start_hour % 1) * 60)
    end_h = int(end_hour)
    end_m = int((end_hour % 1) * 60)

    # Format without minutes if both are :00
    if start_m == 0 and end_m == 0:
        return f"{start_h}-{end_h}"

    # Format with minutes
    start_str = f"{start_h}:{start_m:02d}" if start_m > 0 else str(start_h)
    end_str = f"{end_h}:{end_m:02d}" if end_m > 0 else str(end_h)

    return f"{start_str}-{end_str}"
