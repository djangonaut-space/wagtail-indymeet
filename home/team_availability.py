"""
Team-formation specific availability overlap logic.

These functions build on the generic slot utilities in availability.overlap
but depend on home.models (Team, SessionMembership), so they live here rather
than in the availability app.
"""

from typing import TYPE_CHECKING

from availability.overlap import (
    AvailabilityWindow,
    calculate_overlap,
    find_best_one_hour_windows,
)
from home.models import Team, SessionMembership

if TYPE_CHECKING:
    from accounts.models import CustomUser


def get_role_slots(team: Team, role) -> list[float]:
    """
    Get all unique availability slots from users with a given role on a team.

    Args:
        team: The team to get navigator slots from
        role: The membership role to get slots from

    Returns:
        Sorted list of unique slot values from all users with the role (always as floats)
    """
    members = team.session_memberships.filter(role=role)
    all_slots = set()
    for slots in members.values_list("user__availability__slots", flat=True):
        if slots:
            # Ensure all slots are floats to avoid mixed type arrays
            all_slots.update(float(slot) for slot in slots)
    return sorted(all_slots)


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
