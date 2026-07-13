from django.contrib import admin

from accounts.admin import (
    RelatedUserPastDjangonautFilter,
    RelatedUserPastSessionMemberFilter,
)
from availability.models import UserAvailability
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
