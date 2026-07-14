"""Tests for mapping calendar busy intervals onto the recurring weekly grid."""

from datetime import datetime
from datetime import timezone as dt_timezone

from freezegun import freeze_time

from availability.slots import (
    convert_slot_with_offset,
    current_week_window,
    intervals_to_slots,
    week_start_sunday,
)

UTC = dt_timezone.utc


def test_week_start_sunday_on_sunday():
    sunday_noon = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    assert week_start_sunday(sunday_noon) == datetime(2026, 7, 5, tzinfo=UTC)


def test_week_start_sunday_midweek():
    wednesday = datetime(2026, 7, 8, 23, 59, tzinfo=UTC)
    assert week_start_sunday(wednesday) == datetime(2026, 7, 5, tzinfo=UTC)


def test_convert_slot_with_offset():
    assert convert_slot_with_offset(10.0, 2) == 12.0  # no wrap
    assert convert_slot_with_offset(1.0, -5) == 164.0  # wraps below 0 to week end
    assert convert_slot_with_offset(167.0, 3) == 2.0  # wraps past week end to start


@freeze_time("2026-07-08 12:00:00")  # a Wednesday
def test_current_week_window():
    window_start, window_end, week_start = current_week_window()
    assert week_start == datetime(2026, 7, 5, tzinfo=UTC)  # Sunday
    assert window_start == datetime(2026, 7, 8, tzinfo=UTC)  # today 00:00
    assert window_end == datetime(2026, 7, 12, tzinfo=UTC)  # next Sunday


def test_intervals_to_slots_maps_busy_to_recurring_slots():
    week_start = datetime(2026, 7, 5, tzinfo=UTC)  # Sunday
    window_start = datetime(2026, 7, 8, tzinfo=UTC)  # Wednesday (day 3)
    # Busy Wed 14:00-15:00 UTC -> day 3 -> 72 + 14 = 86.0, plus 86.5
    intervals = [
        (
            datetime(2026, 7, 8, 14, 0, tzinfo=UTC),
            datetime(2026, 7, 8, 15, 0, tzinfo=UTC),
        )
    ]
    assert intervals_to_slots(intervals, week_start, window_start) == {86.0, 86.5}


def test_intervals_before_window_start_are_ignored():
    week_start = datetime(2026, 7, 5, tzinfo=UTC)
    window_start = datetime(2026, 7, 8, tzinfo=UTC)  # today = Wednesday
    # Monday event is earlier in the week than "today" -> not imported.
    intervals = [
        (
            datetime(2026, 7, 6, 9, 0, tzinfo=UTC),
            datetime(2026, 7, 6, 10, 0, tzinfo=UTC),
        )
    ]
    assert intervals_to_slots(intervals, week_start, window_start) == set()


def test_partial_slot_overlap_marks_touched_slots():
    week_start = datetime(2026, 7, 5, tzinfo=UTC)
    window_start = datetime(2026, 7, 5, tzinfo=UTC)
    # Sunday 00:10-00:40 touches the 00:00 and 00:30 slots (0.0 and 0.5).
    intervals = [
        (
            datetime(2026, 7, 5, 0, 10, tzinfo=UTC),
            datetime(2026, 7, 5, 0, 40, tzinfo=UTC),
        )
    ]
    assert intervals_to_slots(intervals, week_start, window_start) == {0.0, 0.5}
