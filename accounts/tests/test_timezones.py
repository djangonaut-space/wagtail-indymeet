"""Tests for availability timezone picker choices."""

from django.test import TestCase
from freezegun import freeze_time

from accounts.timezones import get_timezone_choices
from accounts.timezones import utc_offset_label
from tests.timezones import (
    CENTRAL_EUROPEAN_TIMEZONE,
    DEFAULT_TIMEZONE,
    PACIFIC_AUCKLAND_TIMEZONE,
    QUARTER_HOUR_TIMEZONE,
    US_EASTERN_TIMEZONE,
    UTC_MINUS_FIVE,
    UTC_PLUS_ZERO,
)


@freeze_time("2024-01-15 12:00:00")
class TimezoneChoicesTests(TestCase):
    def test_lists_offsets_not_zone_names(self) -> None:
        choices = get_timezone_choices()
        values = {value for value, _label in choices}

        self.assertEqual(values, {label for _value, label in choices})
        self.assertIn(UTC_MINUS_FIVE, values)
        self.assertIn(UTC_PLUS_ZERO, values)
        self.assertIn("UTC+01:00", values)
        self.assertIn("UTC+05:45", values)
        self.assertIn("UTC+13:00", values)
        self.assertNotIn(US_EASTERN_TIMEZONE, values)
        self.assertNotIn(CENTRAL_EUROPEAN_TIMEZONE, values)
        self.assertNotIn("US/Eastern", values)
        self.assertNotIn("America/Argentina/Buenos_Aires", values)

    def test_offsets_are_ordered_west_to_east(self) -> None:
        labels = [label for _, label in get_timezone_choices()]

        self.assertLess(labels.index(UTC_MINUS_FIVE), labels.index(UTC_PLUS_ZERO))
        self.assertLess(labels.index(UTC_PLUS_ZERO), labels.index("UTC+01:00"))
        self.assertLess(labels.index("UTC+01:00"), labels.index("UTC+13:00"))

    def test_utc_offset_label_maps_iana_zones(self) -> None:
        self.assertEqual(utc_offset_label(US_EASTERN_TIMEZONE), UTC_MINUS_FIVE)
        self.assertEqual(utc_offset_label(CENTRAL_EUROPEAN_TIMEZONE), "UTC+01:00")
        self.assertEqual(utc_offset_label(QUARTER_HOUR_TIMEZONE), "UTC+05:45")
        self.assertEqual(utc_offset_label(PACIFIC_AUCKLAND_TIMEZONE), "UTC+13:00")
        self.assertEqual(utc_offset_label(DEFAULT_TIMEZONE), UTC_PLUS_ZERO)
        self.assertEqual(utc_offset_label(UTC_MINUS_FIVE), UTC_MINUS_FIVE)


@freeze_time("2024-07-15 12:00:00")
class TimezoneChoicesDSTTests(TestCase):
    def test_offsets_follow_daylight_saving(self) -> None:
        values = {value for value, _label in get_timezone_choices()}

        self.assertIn("UTC-04:00", values)
        self.assertIn("UTC+02:00", values)
        self.assertIn("UTC+12:00", values)
        self.assertEqual(utc_offset_label(US_EASTERN_TIMEZONE), "UTC-04:00")
        self.assertEqual(utc_offset_label(CENTRAL_EUROPEAN_TIMEZONE), "UTC+02:00")
        self.assertEqual(utc_offset_label(PACIFIC_AUCKLAND_TIMEZONE), "UTC+12:00")
