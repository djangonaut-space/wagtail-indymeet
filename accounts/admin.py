import csv

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponse

from accounts.models import CustomUser
from accounts.models import Link
from accounts.models import UserAvailability
from accounts.models import UserProfile
from indymeet.admin import DescriptiveSearchMixin


class ExportCsvMixin:
    @admin.action(description="Export Selected")
    def export_as_csv(self, request, queryset):
        """
        Export all fields in a model via django admin
        """
        ignore_fields = ["password", "token", "bio_image"]
        meta = self.model._meta
        field_names = [
            field.name for field in meta.fields if field.name not in ignore_fields
        ]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f"attachment; filename={meta}.csv"
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            exported = []
            for field in field_names:
                if hasattr(obj, field):
                    val = getattr(obj, field)
                else:
                    val = ""
                exported.append(val)
            writer.writerow(exported)
        return response


class LinksInline(admin.StackedInline):
    model = Link
    verbose_name_plural = "links"


@admin.register(CustomUser)
class CustomUserAdmin(ExportCsvMixin, DescriptiveSearchMixin, BaseUserAdmin):
    model = CustomUser
    actions = ["export_as_csv"]


@admin.register(UserProfile)
class UserProfileAdmin(ExportCsvMixin, DescriptiveSearchMixin, admin.ModelAdmin):
    inlines = (LinksInline,)
    model = UserProfile
    actions = ["export_as_csv"]


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
    readonly_fields = ("updated_at",)
    raw_id_fields = ("user",)

    @admin.display(description="Number of Slots")
    def slot_count(self, obj: UserAvailability) -> int:
        """Display the number of availability slots."""
        return len(obj.slots)
