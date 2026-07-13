"""Map concrete calendar busy times onto the recurring weekly grid.

``UserAvailability`` stores a recurring weekly pattern of 30-minute UTC slots
(0.0 = Sunday 00:00 ... 167.5 = Saturday 23:30). Calendar events happen on
concrete dates, so we project the current week's busy intervals onto the grid,
starting from today (earlier days in the week are left untouched).
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

SLOT_INCREMENT = 0.5  # hours per slot (30 minutes)
HOURS_PER_WEEK = 168.0  # 7 days * 24 hours


def week_start_sunday(moment: datetime) -> datetime:
    """Return Sunday 00:00 UTC of the week containing ``moment``.

    The recurring grid is anchored on Sunday, matching ``UserAvailability``.
    """
    moment = moment.astimezone(dt_timezone.utc)
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    # Python weekday(): Monday=0 .. Sunday=6; days since Sunday = (weekday + 1) % 7
    days_since_sunday = (midnight.weekday() + 1) % 7
    return midnight - timedelta(days=days_since_sunday)


def current_week_window(
    now: datetime | None = None,
) -> tuple[datetime, datetime, datetime]:
    """Return ``(window_start, window_end, week_start)`` for the import/overlay.

    - ``week_start``: Sunday 00:00 UTC anchoring the recurring grid.
    - ``window_start``: today 00:00 UTC (earlier days in the week are ignored).
    - ``window_end``: the following Sunday 00:00 UTC (end of the week).
    """
    now = (now or timezone.now()).astimezone(dt_timezone.utc)
    week_start = week_start_sunday(now)
    window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = week_start + timedelta(hours=HOURS_PER_WEEK)
    return window_start, window_end, week_start


def _slot_for(moment: datetime, week_start: datetime) -> float:
    """Hours from ``week_start`` to ``moment`` (may be outside 0..168)."""
    return (moment - week_start).total_seconds() / 3600.0


def intervals_to_slots(
    intervals: list[tuple[datetime, datetime]],
    week_start: datetime,
    window_start: datetime,
) -> set[float]:
    """Project busy ``intervals`` onto recurring 30-minute slot values.

    A slot is marked busy if the 30-minute window it represents overlaps any
    interval. Intervals are clipped to ``[window_start, week_start + 168h)`` so
    that days earlier in the week (before ``window_start``) are never affected.
    """
    window_end = week_start + timedelta(hours=HOURS_PER_WEEK)
    busy: set[float] = set()

    for start, end in intervals:
        start = max(start.astimezone(dt_timezone.utc), window_start)
        end = min(end.astimezone(dt_timezone.utc), window_end)
        if end <= start:
            continue

        first_index = int(_slot_for(start, week_start) // SLOT_INCREMENT)
        # ceil for the exclusive end so a slot only counts when truly overlapped
        end_hours = _slot_for(end, week_start)
        last_index = int(-(-end_hours // SLOT_INCREMENT))  # math.ceil

        for index in range(first_index, last_index):
            slot = index * SLOT_INCREMENT
            if 0.0 <= slot < HOURS_PER_WEEK:
                busy.add(slot)

    return busy
