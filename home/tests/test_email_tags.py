"""Tests for email template tags."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import TestCase

from home.templatetags.email_tags import time_is_link


class TimeIsLinkFilterTests(TestCase):
    """Tests for the time_is_link template filter."""

    def test_time_is_link_with_datetime_uses_time_component(self):
        """Test time_is_link with datetime uses the time from datetime."""
        test_date = datetime(2024, 7, 24, 14, 30, 0)
        result = time_is_link(test_date)

        self.assertEqual(result, "https://time.is/compare/1430_24_July_2024_UTC")

    def test_time_is_link_with_datetime_ignores_custom_time_param(self):
        """Test time_is_link with datetime ignores custom time parameter."""
        test_date = datetime(2024, 7, 24, 14, 30, 0)
        result = time_is_link(test_date, "0900")  # This should be ignored

        # Should use 1430 from datetime, not 0900 from parameter
        self.assertEqual(result, "https://time.is/compare/1430_24_July_2024_UTC")

    def test_time_is_link_with_date_object_uses_time_str(self):
        """Test time_is_link with date object uses time_str parameter."""
        test_date = date(2024, 7, 24)
        result = time_is_link(test_date, "0900")

        self.assertEqual(result, "https://time.is/compare/0900_24_July_2024_UTC")

    def test_time_is_link_with_date_object_default_time(self):
        """Test time_is_link with date object and default time."""
        test_date = date(2024, 7, 24)
        result = time_is_link(test_date)

        self.assertEqual(result, "https://time.is/compare/1200_24_July_2024_UTC")

    def test_time_is_link_with_none_value(self):
        """Test time_is_link with None returns empty string."""
        result = time_is_link(None)

        self.assertEqual(result, "")

    def test_time_is_link_with_timezone_aware_datetime(self):
        """Test time_is_link with timezone-aware datetime."""
        # Create a timezone-aware datetime
        test_date = datetime(
            2024, 7, 24, 14, 30, 0, tzinfo=ZoneInfo("America/New_York")
        )
        result = time_is_link(test_date)

        # Should convert to UTC and use that time component from the datetime
        self.assertEqual(result, "https://time.is/compare/1830_24_July_2024_UTC")
