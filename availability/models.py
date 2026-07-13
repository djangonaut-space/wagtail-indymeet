from django.conf import settings
from django.db import models
from django.urls import reverse

from availability.fields import EncryptedTextField
from availability.managers import (
    CalendarBusyPeriodManager,
    CalendarConnectionManager,
)


class UserAvailability(models.Model):
    """
    Stores a user's general weekly availability in UTC.

    Each availability slot is stored as a number representing hours from
    the start of the week (Sunday 00:00 UTC):
    - Range: 0.0 to 167.5 (7 days * 24 hours, in 0.5 hour increments)
    - Format: hours as float

    Examples:
        - Sunday 00:00 UTC = 0.0
        - Monday 00:00 UTC = 24.0
        - Monday 14:30 UTC = 38.5 (24 + 14.5)
        - Saturday 23:30 UTC = 167.5 (6*24 + 23.5)

    The frontend handles timezone conversion from user's local time to UTC.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability",
    )
    # Store availability as an array of floats representing hours from start of week in UTC
    slots = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Availability"
        verbose_name_plural = "User Availabilities"

    def __str__(self) -> str:
        return f"{self.user}'s availability"

    def add_slot(self, day: int, hour: float) -> None:
        """
        Add a time slot to availability.

        Args:
            day: Day of week (0=Sunday, 6=Saturday)
            hour: Hour in UTC (0.0-23.5 in 0.5 increments)
        """
        slot_value = (day * 24.0) + hour
        if slot_value not in self.slots:
            self.slots.append(slot_value)
            self.slots.sort()

    def remove_slot(self, day: int, hour: float) -> None:
        """
        Remove a time slot from availability.

        Args:
            day: Day of week (0=Sunday, 6=Saturday)
            hour: Hour in UTC (0.0-23.5 in 0.5 increments)
        """
        slot_value = (day * 24.0) + hour
        if slot_value in self.slots:
            self.slots.remove(slot_value)

    def clear_slots(self) -> None:
        """Clear all availability slots."""
        self.slots = []

    def get_slots_for_day(self, day: int) -> list[float]:
        """
        Get all time slots for a specific day.

        Args:
            day: Day of week (0=Sunday, 6=Saturday)

        Returns:
            List of hours (0.0-23.5) available on that day
        """
        day_start = day * 24.0
        day_end = day_start + 24.0
        day_slots = []
        for slot in self.slots:
            if day_start <= slot < day_end:
                # Return the hour within the day (0.0-23.5)
                day_slots.append(slot - day_start)
        return day_slots

    def get_absolute_url(self):
        return reverse("availability")

    def get_full_url(self):
        return settings.BASE_URL + self.get_absolute_url()


class CalendarConnection(models.Model):
    """
    A user's connection to a Google Calendar account used to derive busy times.

    A user can connect more than one Google account; each connection is
    identified by its ``account_label`` (the Google email). OAuth tokens are
    encrypted at rest.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_connections",
    )

    # Human-readable identity of the connected account (e.g. Google email),
    # shown in the UI so users can tell which account is linked.
    account_label = models.CharField(max_length=254, blank=True, default="")

    # --- OAuth credentials (Google) ---
    access_token = EncryptedTextField(blank=True, default="")
    refresh_token = EncryptedTextField(blank=True, default="")
    token_expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(blank=True, default="")

    # --- Sync metadata ---
    # ``last_synced_at`` is the last *successful* sync; the rest add observability.
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_attempted_at = models.DateTimeField(null=True, blank=True)
    # How far into the future the cached busy periods currently reach.
    synced_until = models.DateTimeField(null=True, blank=True)
    # Empty string means the connection is healthy.
    last_sync_error = models.TextField(blank=True, default="")

    # --- Google push-notification (webhook) channel ---
    # ``webhook_channel_id`` is our generated UUID (looked up on incoming
    # notifications); ``webhook_resource_id`` is Google's opaque id, needed to
    # stop the channel; ``webhook_channel_token`` is a shared secret verified on
    # each notification.
    webhook_channel_id = models.CharField(
        max_length=64, blank=True, default="", db_index=True
    )
    webhook_resource_id = models.CharField(max_length=255, blank=True, default="")
    webhook_channel_token = EncryptedTextField(blank=True, default="")
    webhook_expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CalendarConnectionManager()

    class Meta:
        verbose_name = "Calendar Connection"
        verbose_name_plural = "Calendar Connections"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "account_label"],
                name="unique_user_calendar_account",
            )
        ]

    def __str__(self) -> str:
        label = self.account_label or "Google Calendar"
        return f"{self.user}'s {label} connection"


class CalendarBusyPeriod(models.Model):
    """A concrete busy interval cached from a connected calendar.

    Only start/end times are persisted -- never event titles or details. Rows are
    refreshed out-of-band and pruned once stale; see ``availability.providers.service``.
    """

    connection = models.ForeignKey(
        CalendarConnection,
        on_delete=models.CASCADE,
        related_name="busy_periods",
    )
    start = models.DateTimeField()
    end = models.DateTimeField()

    objects = CalendarBusyPeriodManager()

    class Meta:
        verbose_name = "Calendar Busy Period"
        verbose_name_plural = "Calendar Busy Periods"
        ordering = ["start"]
        indexes = [
            models.Index(fields=["connection", "start"]),
            models.Index(fields=["connection", "end"]),
        ]

    def __str__(self) -> str:
        return f"{self.connection} busy {self.start:%Y-%m-%d %H:%M} - {self.end:%H:%M}"
