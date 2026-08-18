"""Shared timezone names used by tests.

These constants keep representative IANA timezone choices in one place so tests
can describe intent without repeating magic strings.
"""

from django.conf import settings

DEFAULT_TIMEZONE = settings.TIME_ZONE
US_EASTERN_TIMEZONE = "America/New_York"
CENTRAL_EUROPEAN_TIMEZONE = "Europe/Berlin"
QUARTER_HOUR_TIMEZONE = "Asia/Kathmandu"
PACIFIC_AUCKLAND_TIMEZONE = "Pacific/Auckland"
UTC_PLUS_ZERO = "UTC+00:00"
UTC_MINUS_FIVE = "UTC-05:00"
