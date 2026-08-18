"""UTC offset choices for the availability picker.

The selector lists distinct offsets currently in effect (``UTC-05:00``,
``UTC+05:45``, …) rather than IANA city names. Saved ``UTC±HH:MM`` values are
fixed offsets; existing IANA names still work for conversion.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from home.slots import UTC_OFFSET_RE

TimezoneChoices = list[tuple[str, str]]


def format_utc_offset(total_minutes: int) -> str:
    """Format a minute offset as ``UTC±HH:MM``."""
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def utc_offset_label(tz_name: str, at: datetime | None = None) -> str:
    """Return the ``UTC±HH:MM`` label for an IANA name or offset string."""
    if not tz_name:
        return format_utc_offset(0)
    if UTC_OFFSET_RE.fullmatch(tz_name):
        return tz_name
    at = at or datetime.now(tz=UTC)
    try:
        offset = at.astimezone(ZoneInfo(tz_name)).utcoffset()
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return format_utc_offset(0)
    if offset is None:
        return format_utc_offset(0)
    return format_utc_offset(int(offset.total_seconds() // 60))


def get_timezone_choices() -> TimezoneChoices:
    """Return unique ``(UTC±HH:MM, UTC±HH:MM)`` choices, west to east."""
    at = datetime.now(tz=UTC)
    offsets: set[int] = set()
    for name in available_timezones():
        try:
            offset = at.astimezone(ZoneInfo(name)).utcoffset()
        except (ZoneInfoNotFoundError, ValueError, OSError):
            continue
        if offset is None:
            continue
        offsets.add(int(offset.total_seconds() // 60))

    return [(format_utc_offset(m), format_utc_offset(m)) for m in sorted(offsets)]
