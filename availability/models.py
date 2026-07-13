from django.conf import settings
from django.db import models
from django.urls import reverse


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
