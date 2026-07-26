"""Tests for availability slot formatting utilities."""

from datetime import datetime

from django.test import TestCase
from freezegun import freeze_time

from availability.formatting import (
    format_availability_by_day,
    format_slot_as_time,
    format_slots_as_ranges,
    format_time_range,
    slot_to_datetime,
)


class FormattingTestCase(TestCase):
    """Test slot formatting utilities."""

    def test_format_slot_as_time(self):
        """Test time formatting."""
        # Sunday 00:00 (12:00 AM)
        self.assertEqual(format_slot_as_time(0.0), "Sun 12:00 AM")

        # Monday 14:30 (2:30 PM)
        self.assertEqual(format_slot_as_time(38.5), "Mon 2:30 PM")

        # Saturday 23:30 (11:30 PM)
        self.assertEqual(format_slot_as_time(167.5), "Sat 11:30 PM")

        # Out-of-range day index falls back to "???"
        self.assertEqual(format_slot_as_time(200.0), "??? 8:00 AM")

    def test_format_slot_as_time_with_offset(self):
        """Offset shifts the slot before formatting, wrapping across the week."""
        # Sunday 00:00 UTC shifted -5 hours wraps back to Saturday evening.
        self.assertEqual(format_slot_as_time(0.0, offset_hours=-5), "Sat 7:00 PM")

    def test_format_slots_as_ranges(self):
        """Test formatting slots as time ranges."""
        # Consecutive slots
        slots = [10.0, 10.5, 11.0, 11.5]
        ranges = format_slots_as_ranges(slots)
        self.assertEqual(len(ranges), 1)
        self.assertIn("Sun", ranges[0])

        # Non-consecutive slots
        slots = [10.0, 10.5, 12.0, 12.5]
        ranges = format_slots_as_ranges(slots)
        self.assertEqual(len(ranges), 2)

        # Empty slots
        ranges = format_slots_as_ranges([])
        self.assertEqual(ranges, [])

    def test_format_slots_as_ranges_with_offset(self):
        """Slots are shifted by the offset before being grouped into ranges."""
        ranges = format_slots_as_ranges([10.0], offset_hours=2)
        self.assertEqual(ranges, ["Sun 12:00 PM - 12:30 PM"])

    def test_format_time_range(self):
        """Test formatting an hour range into 12-hour AM/PM strings."""
        self.assertEqual(format_time_range(7.5, 10.0), "7:30 AM - 10:00 AM")
        self.assertEqual(format_time_range(9.0, 17.0), "9:00 AM - 5:00 PM")

    def test_format_availability_by_day(self):
        """Test grouping slots by day with formatted ranges."""
        result = format_availability_by_day([8.0, 8.5, 34.0])
        self.assertEqual(
            result,
            {
                "Sun": ["8:00 AM - 9:00 AM"],
                "Mon": ["10:00 AM - 10:30 AM"],
            },
        )

        # Empty slots
        self.assertEqual(format_availability_by_day([]), {})

        # Out-of-range slots are dropped rather than crashing
        self.assertEqual(format_availability_by_day([200.0]), {})

    def test_format_availability_by_day_with_offset(self):
        """Slots are shifted by the offset before being grouped by day."""
        result = format_availability_by_day([10.0], offset_hours=2)
        self.assertEqual(result, {"Sun": ["12:00 PM - 12:30 PM"]})

    @freeze_time("2026-07-08")  # a Wednesday
    def test_slot_to_datetime_anchors_to_upcoming_sunday(self):
        self.assertEqual(slot_to_datetime(0.0), datetime(2026, 7, 12, 0, 0))
        self.assertEqual(slot_to_datetime(38.5), datetime(2026, 7, 13, 14, 30))

    @freeze_time("2026-07-05")  # a Sunday
    def test_slot_to_datetime_skips_today_when_today_is_sunday(self):
        # "Next Sunday" should be a week out, not today.
        self.assertEqual(slot_to_datetime(0.0), datetime(2026, 7, 12, 0, 0))
