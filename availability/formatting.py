"""
Formatting helpers for displaying availability slots as human-readable times.

Pure functions that convert slot values (and lists/ranges of slot values)
into display strings. Overlap-calculation logic lives in availability.overlap
instead.
"""

from datetime import datetime, timedelta

from availability.slots import (
    FLOAT_COMPARISON_THRESHOLD,
    SLOT_INCREMENT,
    convert_slot_with_offset,
)


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
