import csv

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import (
    UserAdmin as BaseUserAdmin,
    GroupAdmin as BaseGroupAdmin,
)
from django.contrib.auth.models import Group
from django.contrib import admin as django_admin
from django.core.management import call_command
from django.db.models import Exists, OuterRef, QuerySet
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse

from accounts.models import CustomUser, Link, UserAvailability, UserProfile
from home.models.session import SessionMembership
from indymeet.admin import DescriptiveSearchMixin


class PastSessionMembershipFilter(admin.SimpleListFilter):
    """Base filter for users with a membership in a past session.

    Subclasses set ``title``, ``parameter_name``, and optionally override
    ``membership_queryset``.  Set ``user_field`` to the FK path from the
    filtered model to the user (empty string when the model *is* the user).
    """

    title: str
    parameter_name: str
    user_field: str = ""
    membership_queryset = SessionMembership.objects.all()

    def lookups(
        self, request: admin.ModelAdmin, model_admin: admin.ModelAdmin
    ) -> list[tuple[str, str]]:
        return [
            ("yes", "Yes"),
            ("no", "No"),
        ]

    def queryset(self, request: admin.ModelAdmin, queryset: QuerySet) -> QuerySet:
        if self.value() not in ("yes", "no"):
            return queryset

        outer_ref = self.user_field or "pk"
        annotated = queryset.annotate(
            **{
                self.parameter_name: Exists(
                    self.membership_queryset.filter(user=OuterRef(outer_ref))
                )
            }
        )
        return annotated.filter(**{self.parameter_name: self.value() == "yes"})


class PastDjangonautFilter(PastSessionMembershipFilter):
    title = "past djangonaut"
    parameter_name = "past_djangonaut"
    membership_queryset = SessionMembership.objects.djangonauts()


class PastSessionMemberFilter(PastSessionMembershipFilter):
    title = "past session member"
    parameter_name = "past_session_member"


class RelatedUserPastDjangonautFilter(PastDjangonautFilter):
    user_field = "user"


class RelatedUserPastSessionMemberFilter(PastSessionMemberFilter):
    user_field = "user"


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
    actions = ["export_as_csv", "compare_availability_action"]
    search_fields = (
        "first_name",
        "last_name",
        "email",
        "username",
        "profile__github_username",
    )
    list_select_related = ("profile",)
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "profile__github_username",
        "date_joined",
    )
    list_filter = (PastDjangonautFilter, PastSessionMemberFilter)

    @admin.action(description="Compare availability of selected users")
    def compare_availability_action(
        self, request, queryset
    ) -> HttpResponseRedirect | None:
        """Redirect to compare availability page with selected user IDs."""
        user_ids = list(queryset.values_list("id", flat=True))
        if not user_ids:
            self.message_user(
                request,
                "Please select at least one user.",
                messages.ERROR,
            )
            return None

        url = reverse("compare_availability")
        return HttpResponseRedirect(f"{url}?users={','.join(map(str, user_ids))}")


@admin.register(UserProfile)
class UserProfileAdmin(ExportCsvMixin, DescriptiveSearchMixin, admin.ModelAdmin):
    inlines = (LinksInline,)
    model = UserProfile
    actions = ["export_as_csv"]
    list_filter = (RelatedUserPastDjangonautFilter, RelatedUserPastSessionMemberFilter)


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


class UserModelInline(admin.TabularInline):
    extra = 1
    model = CustomUser.groups.through
    autocomplete_fields = ["customuser"]


# Unregister default GroupAdmin and register custom version
django_admin.site.unregister(Group)


@admin.register(Group)
class CustomGroupAdmin(BaseGroupAdmin):
    """Custom Group admin with Session Organizers management action."""

    inlines = [UserModelInline]

    @admin.action(description="Recreate Session Organizers group permissions")
    def recreate_session_organizers_group(self, request, queryset) -> None:
        """Recreate the Session Organizers group with up-to-date permissions."""
        call_command("setup_session_organizers_group")
        self.message_user(
            request,
            "Successfully recreated Session Organizers group permissions.",
            messages.SUCCESS,
        )

    actions = ["recreate_session_organizers_group"]
