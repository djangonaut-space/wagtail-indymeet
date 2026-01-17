"""Template tags for email templates."""

from datetime import datetime, date
from typing import Union
from zoneinfo import ZoneInfo

from django import template

register = template.Library()


@register.filter
def time_is_link(date_value: datetime | date, time_str: str = "1200") -> str:
    """
    Generate a time.is comparison link for a given date and time in UTC.

    If date_value is a datetime, it's converted to UTC and the time component is used.
    If date_value is a date, the time_str parameter is used.

    Args:
        date_value: The date to convert (datetime or date object)
        time_str: Time in HHMM format (default: "1200" for 12:00), only used for date objects

    Returns:
        A URL to time.is with the formatted date and time in UTC

    Example:
        {{ some_date|time_is_link:"1200" }}  # date object uses time_str
        -> https://time.is/compare/1200_24_July_2024_UTC

        {{ some_datetime|time_is_link }}  # datetime converted to UTC, uses UTC time
        -> https://time.is/compare/1430_24_July_2024_UTC
    """
    if not date_value:
        return ""

    # If it's a datetime object, convert to UTC and extract its time component
    if isinstance(date_value, datetime):
        # Convert timezone-aware datetime to UTC, or assume naive datetime is UTC
        if date_value.tzinfo is not None:
            date_value = date_value.astimezone(ZoneInfo("UTC"))
        time_str = date_value.strftime("%H%M")

    # Format: HHMM_DD_Month_YYYY_UTC
    formatted_date = date_value.strftime(f"{time_str}_%d_%B_%Y_UTC")
    return f"https://time.is/compare/{formatted_date}"
