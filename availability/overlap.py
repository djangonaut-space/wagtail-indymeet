"""
Utility functions for calculating availability overlaps between users.

These are generic slot/time helpers over UserAvailability. Team-formation
specific overlap logic (which depends on home.models) lives in
home.team_availability instead. Display formatting for slot values lives in
availability.formatting.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from availability.formatting import format_slot_as_time, slot_to_datetime
from availability.slots import (
    FLOAT_COMPARISON_THRESHOLD,
    HOURS_PER_WEEK,
    SLOT_INCREMENT,
)

if TYPE_CHECKING:
    from accounts.models import CustomUser


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
    def start_datetime(self) -> datetime:
        """
        Return a datetime object representing the start of this window.

        Uses a reference date (next Sunday from today) to create an actual
        datetime that can be used with templatetags like time_is_link.

        Returns:
            UTC datetime for the start of this availability window
        """
        return slot_to_datetime(self.slot_range[0])


def get_user_slots(user: "CustomUser") -> list[float]:
    """
    Get availability slots for a user.

    Args:
        user: A CustomUser instance

    Returns:
        List of float values representing 30-minute time slots (0.0-167.5)
        Returns empty list if user has no availability set
    """
    return user.availability.slots if hasattr(user, "availability") else []


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
