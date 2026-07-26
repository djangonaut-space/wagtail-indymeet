from django.contrib import admin

from accounts.admin import (
    RelatedUserPastDjangonautFilter,
    RelatedUserPastSessionMemberFilter,
)
from availability.models import CalendarConnection, UserAvailability
from indymeet.admin import DescriptiveSearchMixin


@admin.register(UserAvailability)
class UserAvailabilityAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    """Admin interface for UserAvailability."""

    list_display = ("user", "slot_count", "updated_at")
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    list_filter = (
        RelatedUserPastDjangonautFilter,
        RelatedUserPastSessionMemberFilter,
        "updated_at",
    )
    readonly_fields = ("updated_at",)
    raw_id_fields = ("user",)

    @admin.display(description="Number of Slots")
    def slot_count(self, obj: UserAvailability) -> int:
        """Display the number of availability slots."""
        return len(obj.slots)


@admin.register(CalendarConnection)
class CalendarConnectionAdmin(admin.ModelAdmin):
    """Admin interface for CalendarConnection.

    Encrypted credential fields are intentionally excluded from the admin so
    tokens and secret URLs are never rendered in the UI.
    """

    list_display = ("user", "account_label", "last_synced_at", "updated_at")
    list_filter = ("updated_at", "last_synced_at")
    search_fields = (
        "user__username",
        "user__email",
        "account_label",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "last_synced_at",
        "last_sync_attempted_at",
        "synced_until",
        "last_sync_error",
        "token_expiry",
        "webhook_expires_at",
    )
    raw_id_fields = ("user",)
    fields = (
        "user",
        "account_label",
        "scopes",
        "token_expiry",
        "last_synced_at",
        "last_sync_attempted_at",
        "synced_until",
        "last_sync_error",
        "webhook_expires_at",
        "created_at",
        "updated_at",
    )
