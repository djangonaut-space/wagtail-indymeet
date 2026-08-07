"""
Weekly availability slot primitives.

A "slot" is a 30-minute position within a recurring week, expressed as hours
from Sunday 00:00 (``0.0`` through ``167.5``). A bare float carries no timezone,
so the same number means different instants for different users. :class:`Slot`
binds a slot value to the timezone it was recorded in and derives every other
representation (UTC, another viewer's timezone, display strings) from that pair.

This module deliberately imports only the standard library. ``accounts.models``
imports :class:`Slot`, and ``home.availability`` imports ``accounts.models``,
so any Django model import here would create an import cycle.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import cached_property, lru_cache
from zoneinfo import ZoneInfo

# Constants for availability calculations
SLOT_INCREMENT = 0.5  # Each slot represents 30 minutes
FLOAT_COMPARISON_THRESHOLD = 0.01  # Threshold for float equality checks
HOURS_PER_WEEK = 168  # Total hours in a week (7 days * 24 hours)

DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

UTC = ZoneInfo("UTC")


def _as_zoneinfo(value: "str | ZoneInfo") -> ZoneInfo:
    """Normalize an IANA timezone name or ``ZoneInfo`` into a ``ZoneInfo``."""
    return value if isinstance(value, ZoneInfo) else ZoneInfo(value)


@lru_cache(maxsize=1)
def _week_start_for(today: date) -> date:
    """Return the Sunday starting ``today``'s week.

    Keyed on the date so the single cache entry falls out of date on its own:
    every slot conversion needs this value, but a long-running process must
    still follow the calendar across midnight.
    """
    return today - timedelta(days=(today.weekday() + 1) % 7)


def _reference_week_start() -> date:
    """Return the Sunday starting this week, for timezone conversion.

    Availability is stored as hours from Sunday 00:00, so timezone conversion
    needs a real calendar week to apply the correct UTC offset/DST rules.

    Example:
        On a Monday, June 17 2024, this returns ``date(2024, 6, 16)`` because
        that week starts on Sunday, June 16.
    """
    return _week_start_for(datetime.now().date())


def _slot_datetime_components(slot: float) -> tuple[int, int, int]:
    """Return day offset, hour, and minute components for a weekly slot."""
    day_offset = int(slot // 24)
    hour_in_day = slot % 24
    hours = int(hour_in_day)
    minutes = round((hour_in_day % 1) * 60)
    if minutes == 60:
        hours += 1
        minutes = 0
    return day_offset, hours, minutes


def _datetime_to_slot(value: datetime, week_start: date) -> float:
    """Convert a datetime to a wall-clock weekly slot.

    Use calendar day/hour components rather than elapsed seconds so DST gaps or
    folds within the week do not shift the wall-clock slot number.
    """
    day_offset = (value.date() - week_start).days
    hours = value.hour + (value.minute / 60)
    return round(((day_offset * 24) + hours) % HOURS_PER_WEEK, 6)


def _slot_to_datetime(
    slot: float,
    timezone_name: "str | ZoneInfo" = "UTC",
    week_start: "date | None" = None,
) -> datetime:
    """
    Convert a weekly slot value to a timezone-aware datetime.

    This creates a concrete datetime for this week (Sunday-Saturday). The date
    is arbitrary because availability is weekly and recurring, but anchoring
    slots to a real week lets zoneinfo apply that week's UTC offset/DST rules.

    Ambiguous or nonexistent local times intentionally inherit Python
    ``datetime``/``zoneinfo`` defaults (``fold=0`` and no validation). The first
    pass documents that behavior instead of blocking rare DST edge cells in the UI.
    """
    if week_start is None:
        week_start = _reference_week_start()
    day_offset, hours, minutes = _slot_datetime_components(slot)
    target_date = week_start + timedelta(days=day_offset)
    return datetime.combine(
        target_date,
        time(hour=hours, minute=minutes),
        tzinfo=_as_zoneinfo(timezone_name),
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


def _format_local_slot_as_time(slot: float) -> str:
    """Format a local wall-clock weekly slot without timezone conversion."""

    day_index = int(slot // 24)
    hour_in_day = slot % 24
    hours24 = int(hour_in_day)
    minutes = round((hour_in_day % 1) * 60)
    if minutes == 60:
        hours24 += 1
        minutes = 0

    # Convert to 12-hour format with AM/PM.
    hours12, period = _convert_to_12hour_format(hours24 % 24)

    day_name = DAYS[day_index] if 0 <= day_index < 7 else "???"

    return f"{day_name} {hours12}:{minutes:02d} {period}"


@dataclass(frozen=True, eq=False)
class Slot:
    """
    A 30-minute weekly availability slot bound to the timezone it was saved in.

    ``value`` is a wall-clock weekly position (hours from Sunday 00:00) as read
    from ``UserAvailability.slots``, and ``timezone`` is that row's
    ``slots_timezone``. Every other view of the slot -- UTC, an arbitrary
    viewer timezone, display strings -- is derived, so callers never have to
    track which timezone a loose float belonged to.

    Two slots are equal when they refer to the same instant in the reference
    week, *regardless of the timezone they were recorded in*. That is what
    makes cross-user overlap work: a Djangonaut in Chicago and a navigator in
    Berlin who are free at the same moment produce equal, equally-hashing slots,
    so ``set.intersection`` over different users' slots behaves correctly.

    .. warning::
        Equality and hashing depend on *which week the slot was built in*.
        Availability is recurring, so a slot is anchored to the current
        calendar week (see :func:`_reference_week_start`) to pick up that
        week's UTC offset. Across a DST transition the same wall-clock value
        resolves to a different instant -- ``Slot("America/New_York", 33.0)``
        has ``slot_utc`` 37.0 in July and 38.0 in December -- so two such slots
        compare unequal. That is correct, but it means slots must not be
        cached, pickled, or held in a set across a DST boundary: build them
        from ``UserAvailability.slots`` per request and discard them.

    Example:
        >>> Slot("America/New_York", 33.0).format_utc  # Mon 09:00 in New York
        'Mon 1:00 PM'
    """

    #: Weekday abbreviations indexed by :attr:`day_index` (0=Sunday).
    DAY_NAMES = DAYS

    timezone: ZoneInfo
    value: float

    def __post_init__(self) -> None:
        # Accept plain IANA names so callers can pass ``slots_timezone`` directly.
        object.__setattr__(self, "timezone", _as_zoneinfo(self.timezone))
        object.__setattr__(self, "value", float(self.value))

    def __repr__(self) -> str:
        return f"Slot({str(self.timezone)!r}, {self.value!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Slot):
            return NotImplemented
        return self.slot_utc == other.slot_utc

    def __hash__(self) -> int:
        return hash(self.slot_utc)

    def __lt__(self, other: "Slot") -> bool:
        if not isinstance(other, Slot):
            return NotImplemented
        return self.slot_utc < other.slot_utc

    @cached_property
    def _week_start(self) -> date:
        """The calendar week this slot is anchored to.

        Held per instance so a slot's own conversions stay mutually consistent
        even if the process crosses midnight between accesses.
        """
        return _reference_week_start()

    @cached_property
    def local(self) -> datetime:
        """The slot as an aware datetime in its own timezone."""
        return _slot_to_datetime(self.value, self.timezone, self._week_start)

    @cached_property
    def utc(self) -> datetime:
        """The slot as an aware datetime in UTC."""
        return self.local.astimezone(UTC)

    @property
    def slot_local(self) -> float:
        """The wall-clock weekly slot value in this slot's own timezone."""
        return self.value

    @cached_property
    def slot_utc(self) -> float:
        """The comparable UTC weekly slot value."""
        return _datetime_to_slot(self.utc, self._week_start)

    @property
    def format_local(self) -> str:
        """Display string in this slot's own timezone, e.g. ``"Mon 9:00 AM"``."""
        return _format_local_slot_as_time(self.slot_local)

    @property
    def format_utc(self) -> str:
        """Display string in UTC, e.g. ``"Mon 1:00 PM"``."""
        return _format_local_slot_as_time(self.slot_utc)

    @property
    def format_time_only(self) -> str:
        """Display string without the weekday, e.g. ``"9:00 AM"``."""
        return self.format_local.split(" ", 1)[1]

    def as_tz(self, tz: "str | ZoneInfo") -> datetime:
        """Return this slot as an aware datetime in ``tz``."""
        return self.utc.astimezone(_as_zoneinfo(tz))

    def slot_as_tz(self, tz: "str | ZoneInfo") -> float:
        """
        Return the wall-clock weekly slot value as seen from ``tz``.

        Stays a float because slots move in 0.5 steps: truncating to ``int``
        would silently collapse every half-hour slot onto the hour.
        """
        return _datetime_to_slot(self.as_tz(tz), self._week_start)

    def format_as_tz(self, tz: "str | ZoneInfo") -> str:
        """Return the display string as seen from ``tz``."""
        return _format_local_slot_as_time(self.slot_as_tz(tz))

    def in_tz(self, tz: "str | ZoneInfo") -> "Slot":
        """
        Return an equal slot re-expressed in ``tz``.

        The result refers to the same instant -- so it compares and hashes equal
        to this slot -- but its ``value``, ``day_index`` and ``format_local``
        read in ``tz``. Use it to move a set of UTC slots into a viewer's
        timezone before grouping or display.
        """
        return Slot(tz, self.slot_as_tz(tz))

    @property
    def day_index(self) -> int:
        """Day of the week in this slot's own timezone (0=Sunday)."""
        return int(self.value // 24)

    @property
    def day_name(self) -> str:
        """Abbreviated weekday name in this slot's own timezone."""
        return DAYS[self.day_index] if 0 <= self.day_index < 7 else "???"

    @property
    def hour_in_day(self) -> float:
        """Hours past midnight in this slot's own timezone (0.0-23.5)."""
        return self.value % 24

    @property
    def key(self) -> str:
        """
        Stable identifier for this slot's position in its own timezone's week.

        Used to key a slot's data for template and JavaScript consumers, which
        treat it as an opaque string. Two slots referring to the same instant
        from different timezones get *different* keys, because the key names a
        wall-clock position -- a grid cell -- not an instant.
        """
        return f"{self.day_index}-{self.hour_in_day:g}"

    def __add__(self, hours: float) -> "Slot":
        """Return the slot ``hours`` later, wrapping around the week."""
        return Slot(self.timezone, (self.value + hours) % HOURS_PER_WEEK)

    def is_adjacent_to(self, other: "Slot") -> bool:
        """
        Whether ``other`` is the next 30-minute slot after this one.

        Compares instants with a tolerance because slot values are floats and
        non-hour-aligned timezones introduce quarter-hour remainders.
        """
        delta = other.slot_utc - self.slot_utc
        return abs(delta - SLOT_INCREMENT) < FLOAT_COMPARISON_THRESHOLD
