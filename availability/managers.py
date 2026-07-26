"""QuerySets and managers for the availability app.

The busy-period and connection filters (overlapping, stale, prunable) live here
as chainable QuerySet methods so the rules are defined once and testable
directly against the database.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from django.db import models
from django.db.models import Q


class CalendarBusyPeriodQuerySet(models.QuerySet):
    """Queries over cached busy intervals (``CalendarBusyPeriod``)."""

    def overlapping(self, start: datetime, end: datetime) -> CalendarBusyPeriodQuerySet:
        """Periods overlapping the half-open window ``[start, end)`` (abutting excluded)."""
        return self.filter(start__lt=end, end__gt=start)

    def for_users(self, users: Iterable) -> CalendarBusyPeriodQuerySet:
        """Periods belonging to any of ``users`` via their connections."""
        return self.filter(connection__user__in=users)

    def ending_after(self, moment: datetime) -> CalendarBusyPeriodQuerySet:
        """Periods that end strictly after ``moment`` (the future-facing rows)."""
        return self.filter(end__gt=moment)

    def ending_before(self, moment: datetime) -> CalendarBusyPeriodQuerySet:
        """Periods that end strictly before ``moment`` (prunable stale rows)."""
        return self.filter(end__lt=moment)


class CalendarConnectionQuerySet(models.QuerySet):
    """Queries over calendar connections (``CalendarConnection``)."""

    def for_users(self, users: Iterable) -> CalendarConnectionQuerySet:
        """Connections owned by any of ``users``."""
        return self.filter(user__in=users)

    def stale(self, cutoff: datetime) -> CalendarConnectionQuerySet:
        """Connections never synced or last synced before ``cutoff`` (eligible for refresh)."""
        return self.filter(
            Q(last_synced_at__isnull=True) | Q(last_synced_at__lt=cutoff)
        )


CalendarBusyPeriodManager = models.Manager.from_queryset(CalendarBusyPeriodQuerySet)
CalendarConnectionManager = models.Manager.from_queryset(CalendarConnectionQuerySet)
