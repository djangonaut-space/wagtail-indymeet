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
from django.http import HttpResponseRedirect
from django.urls import reverse
from import_export.admin import ExportMixin, ImportExportModelAdmin
from import_export.fields import Field
from import_export.resources import ModelResource
from import_export.widgets import ForeignKeyWidget

from accounts.models import (
    ButtondownAccount,
    CustomUser,
    DiscordMember,
    DiscordRole,
    Link,
    UserAvailability,
    UserProfile,
)
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


class CustomUserResource(ModelResource):
    """Export resource for CustomUser, including the profile fields shown in list_display."""

    github_username = Field(
        column_name="github_username", attribute="profile__github_username"
    )
    discord_username = Field(
        column_name="discord_username", attribute="profile__discord_member__username"
    )
    discord_nickname = Field(
        column_name="discord_nickname", attribute="profile__discord_member__nickname"
    )

    class Meta:
        model = CustomUser
        exclude = ("password",)


class UserProfileResource(ModelResource):
    """Import/export resource for linking a UserProfile to a Discord member by username."""

    discord_username = Field(
        column_name="discord_username",
        attribute="discord_member",
        widget=ForeignKeyWidget(DiscordMember, field="username"),
    )

    class Meta:
        model = UserProfile
        fields = ("id", "user", "discord_username")
        export_order = fields


class DiscordMemberResource(ModelResource):
    """Export resource for DiscordMember, limited to the model's own fields."""

    class Meta:
        model = DiscordMember


class LinksInline(admin.StackedInline):
    model = Link
    verbose_name_plural = "links"


@admin.register(CustomUser)
class CustomUserAdmin(ExportMixin, DescriptiveSearchMixin, BaseUserAdmin):
    model = CustomUser
    resource_class = CustomUserResource
    actions = ["compare_availability_action"]
    search_fields = (
        "first_name",
        "last_name",
        "email",
        "username",
        "profile__github_username",
        "profile__discord_member__nickname",
        "profile__discord_member__discord_id",
    )
    list_select_related = ("profile", "profile__discord_member")
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "profile__github_username",
        "profile__discord_member",
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
class UserProfileAdmin(
    ImportExportModelAdmin, DescriptiveSearchMixin, admin.ModelAdmin
):
    inlines = (LinksInline,)
    model = UserProfile
    resource_class = UserProfileResource
    list_display = ("user", "github_username", "discord_member")
    list_select_related = ("user", "discord_member")
    autocomplete_fields = (
        "discord_member",
        "user",
    )
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "github_username",
        "discord_member__nickname",
        "discord_member__discord_id",
    )
    list_filter = (RelatedUserPastDjangonautFilter, RelatedUserPastSessionMemberFilter)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "discord_member":
            kwargs["queryset"] = DiscordMember.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(DiscordRole)
class DiscordRoleAdmin(admin.ModelAdmin):
    """Read-only view of the roles an announcement can ping.

    The rows are a mirror of the Discord server, rewritten wholesale by the
    Discord session setup action and the ``sync_discord_roles`` command, so
    editing them here would only be undone on the next sync.
    """

    list_display = ("name", "discord_id", "updated_at")
    search_fields = ("name",)
    readonly_fields = ("name", "discord_id", "created_at", "updated_at")

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(DiscordMember)
class DiscordMemberAdmin(ExportMixin, admin.ModelAdmin):
    """Read-only view of guild members mirrored from Discord."""

    resource_class = DiscordMemberResource
    list_display = (
        "username",
        "nickname",
        "discord_id",
    )
    search_fields = ("username", "nickname", "discord_id")
    readonly_fields = (
        "discord_id",
        "username",
        "nickname",
        "role_ids",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(ButtondownAccount)
class ButtondownAccountAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    model = ButtondownAccount
    search_fields = ["buttondown_identifier", "user__email"]
    list_display = ["user", "buttondown_identifier"]
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
