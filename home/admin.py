from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Exists, F, Max, Count, OuterRef
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from import_export import fields, resources
from import_export.admin import ExportMixin

from indymeet.admin import DescriptiveSearchMixin
from . import preview_email, tasks
from .availability import AvailabilityWindow, find_best_one_hour_windows_with_roles
from .forms import SurveyCSVExportForm, SurveyCSVImportForm
from .models import Event, Project, Team, Testimonial
from .models import ResourceLink
from .models import Question
from .models import Session
from .models import SessionMembership
from .models import Survey
from .models import UserQuestionResponse
from .models import UserSurveyResponse as UserSurveyResponseModel
from .models import Waitlist
from .team_allocation import allocate_teams_bounded_search, apply_allocation
from .views.team_formation import (
    add_to_waitlist,
    calculate_overlap_ajax,
    team_formation_view,
)
from .views.session_notifications import (
    send_acceptance_reminders_view,
    send_session_results_view,
    send_team_welcome_emails_view,
)

User = get_user_model()


@admin.register(Event)
class EventAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    model = Event
    filter_horizontal = ("speakers", "rsvped_members", "organizers")


@admin.register(Project)
class ProjectAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    list_display = ("name", "url")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(ResourceLink)
class ResourceLinkAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    list_display = (
        "path",
        "link",
        "url",
        "permanent",
        "updated",
        "created",
    )
    ordering = ("path",)
    search_fields = ("path", "url")

    @admin.display(description="Link", ordering="path")
    def link(self, obj):
        href = reverse("resource_link", kwargs={"path": obj.path})
        return mark_safe(f'<a href="{href}">Copy to share</a>')


class UserWithMembershipFilter(admin.SimpleListFilter):
    """Filter SessionMembership by user, showing only users with memberships."""

    title = "user"
    parameter_name = "user"

    def lookups(self, request, model_admin):
        """Return list of users who have session memberships."""
        users = (
            User.objects.filter(session_memberships__isnull=False)
            .distinct()
            .order_by("first_name", "last_name", "email")
        )

        return [
            (
                user.id,
                user.get_full_name() or user.email,
            )
            for user in users
        ]

    def queryset(self, request, queryset):
        """Filter the queryset based on selected user."""
        if self.value():
            return queryset.filter(user_id=self.value())
        return queryset


class SessionMembershipInline(admin.TabularInline):
    model = SessionMembership
    autocomplete_fields = ["user"]
    extra = 0

    def get_queryset(self, request):
        """Filter memberships to only those for organized sessions."""
        return super().get_queryset(request).for_admin_site(request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit team choices to teams in the current session."""
        if db_field.name == "team":
            # Get the session from the parent object being edited
            session_id = request.resolver_match.kwargs.get("object_id")
            if session_id:
                kwargs["queryset"] = Team.objects.filter(session_id=session_id)
            else:
                # No session determined (shouldn't happen in normal usage)
                kwargs["queryset"] = Team.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class SessionMembershipResource(resources.ModelResource):
    """Export resource for SessionMembership with related data."""

    user_email = fields.Field(column_name="user_email", attribute="user__email")
    user_first_name = fields.Field(
        column_name="user_first_name", attribute="user__first_name"
    )
    user_last_name = fields.Field(
        column_name="user_last_name", attribute="user__last_name"
    )
    session_title = fields.Field(
        column_name="session_title", attribute="session__title"
    )
    team_name = fields.Field(column_name="team_name", attribute="team__name")
    github_username = fields.Field(
        column_name="github_username", attribute="user__profile__github_username"
    )
    navigator = fields.Field(column_name="navigator", readonly=True)
    captain = fields.Field(column_name="captain", readonly=True)

    class Meta:
        model = SessionMembership
        fields = (
            "id",
            "user_email",
            "user_first_name",
            "user_last_name",
            "session_title",
            "role",
            "team_name",
            "github_username",
            "navigator",
            "captain",
            "accepted",
            "acceptance_deadline",
            "accepted_at",
        )
        export_order = fields

    def dehydrate_navigator(self, membership: SessionMembership) -> str:
        """Get navigator email(s) for the team."""
        if not membership.team:
            return ""
        navigators = membership.team.session_memberships.navigators()
        return ", ".join([n.user.email for n in navigators])

    def dehydrate_captain(self, membership: SessionMembership) -> str:
        """Get captain email(s) for the team."""
        if not membership.team:
            return ""
        captains = membership.team.session_memberships.captains()
        return ", ".join([c.user.email for c in captains])


@admin.register(SessionMembership)
class SessionMembershipAdmin(ExportMixin, DescriptiveSearchMixin, admin.ModelAdmin):
    resource_class = SessionMembershipResource

    list_display = (
        "user",
        "user_email",
        "session",
        "role",
        "team",
        "navigator",
        "captain",
        "github_username",
        "accepted",
        "acceptance_deadline",
    )
    list_filter = ("session", "role", "accepted", UserWithMembershipFilter)
    search_fields = ("user__email", "user__first_name", "user__last_name")
    readonly_fields = ("accepted_at",)
    actions = [
        "send_acceptance_emails_action",
        "find_best_availability_overlaps_action",
        "compare_availability_action",
        preview_email.acceptance_email_action,
        preview_email.reminder_email_action,
    ]

    @admin.display(description="User Email", ordering="user__email")
    def user_email(self, obj: SessionMembership) -> str:
        return obj.user.email

    @admin.display(description="Navigator")
    def navigator(self, obj: SessionMembership) -> str:
        if not obj.team:
            return "-"
        # Do the filtering at the app level since we're prefetching
        # all of the membership of the team to avoid N+1 queries.
        emails = [
            membership.user.email
            for membership in obj.team.session_memberships.all()
            if membership.role == SessionMembership.NAVIGATOR
        ]
        return ", ".join(emails) or "-"

    @admin.display(description="Captain")
    def captain(self, obj: SessionMembership) -> str:
        if not obj.team:
            return "-"
        # Do the filtering at the app level since we're prefetching
        # all of the membership of the team to avoid N+1 queries.
        emails = [
            membership.user.email
            for membership in obj.team.session_memberships.all()
            if membership.role == SessionMembership.CAPTAIN
        ]
        return ", ".join(emails) or "-"

    @admin.display(description="GitHub", ordering="user__profile__github_username")
    def github_username(self, obj: SessionMembership) -> str:
        if hasattr(obj.user, "profile") and obj.user.profile.github_username:
            return obj.user.profile.github_username
        return "-"

    def get_queryset(self, request):
        """Optimize queryset and filter to organized sessions."""
        return (
            super()
            .get_queryset(request)
            .select_related("user__profile", "session", "team")
            .prefetch_related("team__session_memberships__user")
            .for_admin_site(request.user)
        )

    def save_model(self, request, obj: SessionMembership, form, change: bool) -> None:
        """Show reminder for superuser organizers to review group permissions."""
        super().save_model(request, obj, form, change)

        # When creating a session organizer
        if obj.role == SessionMembership.ORGANIZER and request.user.is_superuser:
            group = Group.objects.filter(name="Session Organizers").first()
            if group:
                group_url = reverse("admin:auth_group_change", args=[group.pk])
                message = mark_safe(
                    f'Review the <a href="{group_url}" target="_blank">'
                    "Session Organizers group</a> to remove those who shouldn't "
                    "have access anymore."
                )
                self.message_user(request, message, messages.INFO)

    @admin.action(description="Send acceptance emails to selected members")
    def send_acceptance_emails_action(self, request, queryset):
        """
        Send acceptance emails to selected SessionMembership records.

        This action enqueues acceptance notification emails to users with
        SessionMembership records, typically after team formation.
        """
        djangonauts = queryset.djangonauts()
        queued_count = 0

        for membership in djangonauts:
            tasks.send_membership_acceptance_email.enqueue(
                membership_id=membership.pk,
            )
            queued_count += 1

        self.message_user(
            request,
            f"Successfully queued {queued_count} acceptance email(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Find overlapping availability time slots")
    def find_best_availability_overlaps_action(self, request, queryset):
        """
        Find and display top 5 one-hour time slots with most member availability.

        For each time slot, shows:
        - Total count of available members
        - Count by role (Djangonaut, Captain, Navigator, Organizer)
        - Link to view members who are NOT available during that time
        """
        if queryset.count() < 2:
            self.message_user(
                request,
                "Please select at least 2 members to find overlapping availability.",
                messages.ERROR,
            )
            return

        queryset = queryset.select_related("user").prefetch_related(
            "user__availability"
        )
        user_roles = {m.user: m.role for m in queryset}
        results = find_best_one_hour_windows_with_roles(
            user_roles=user_roles,
            top_n=10,
        )

        if not results:
            self.message_user(
                request,
                "No overlapping 1-hour availability found among selected members.",
                messages.WARNING,
            )
            return
        message = render_to_string(
            "admin/availability_overlap_message.html",
            {"results": results, "total_members": len(user_roles)},
        )
        self.message_user(request, mark_safe(message))

    @admin.action(description="Compare availability (visual calendar)")
    def compare_availability_action(
        self, request, queryset
    ) -> HttpResponseRedirect | None:
        """Redirect to compare availability page with selected membership user IDs."""
        queryset = queryset.select_related("session")

        # Get unique user IDs from the selected memberships
        user_ids = list(queryset.values_list("user_id", flat=True).distinct())
        if not user_ids:
            self.message_user(
                request,
                "Please select at least one member.",
                messages.ERROR,
            )
            return None

        # Get session ID if all selected memberships are from the same session
        session_ids = list(queryset.values_list("session_id", flat=True).distinct())

        url = reverse("compare_availability")
        params = f"users={','.join(map(str, user_ids))}"

        if len(session_ids) == 1:
            params += f"&session={session_ids[0]}"

        return HttpResponseRedirect(f"{url}?{params}")


@admin.register(Session)
class SessionAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    inlines = [SessionMembershipInline]
    filter_horizontal = ("available_projects",)
    actions = [
        "auto_allocate_teams_action",
        preview_email.rejection_email_action,
        preview_email.waitlist_email_action,
        preview_email.team_welcome_email_action,
    ]
    list_display = ("title", "start_date", "end_date", "form_teams", "email_actions")

    @admin.display(description="Form Teams")
    def form_teams(self, obj):
        href = reverse("admin:session_form_teams", kwargs={"session_id": obj.id})
        return mark_safe(f'<a href="{href}">Form Teams</a>')

    @admin.display(description="Email Actions")
    def email_actions(self, obj):
        actions = [
            (
                "Send application results",
                reverse("admin:session_send_results", args=[obj.id]),
            ),
            (
                "Send acceptance reminder emails",
                reverse("admin:session_send_acceptance_reminders", args=[obj.id]),
            ),
            (
                "Send team welcome emails",
                reverse("admin:session_send_team_welcome_emails", args=[obj.id]),
            ),
        ]
        return mark_safe(
            "<br />".join([f"<a href={href}>{action}</a>" for action, href in actions])
        )

    def get_urls(self):
        """Add custom URLs for team formation and notifications"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:session_id>/form-teams/",
                self.admin_site.admin_view(team_formation_view),
                name="session_form_teams",
            ),
            path(
                "<int:session_id>/add-to-waitlist/",
                self.admin_site.admin_view(add_to_waitlist),
                name="session_add_to_waitlist",
            ),
            path(
                "<int:session_id>/calculate-overlap/",
                self.admin_site.admin_view(calculate_overlap_ajax),
                name="session_calculate_overlap",
            ),
            path(
                "<int:session_id>/send-session-results/",
                self.admin_site.admin_view(send_session_results_view),
                name="session_send_results",
            ),
            path(
                "<int:session_id>/send-acceptance-reminders/",
                self.admin_site.admin_view(send_acceptance_reminders_view),
                name="session_send_acceptance_reminders",
            ),
            path(
                "<int:session_id>/send-team-welcome-emails/",
                self.admin_site.admin_view(send_team_welcome_emails_view),
                name="session_send_team_welcome_emails",
            ),
        ]
        return custom_urls + urls

    @admin.action(description="Auto-allocate Djangonauts to teams")
    def auto_allocate_teams_action(self, request, queryset):
        """
        Automatically allocate Djangonauts to teams using the allocation algorithm.

        This action:
        - Analyzes all eligible applicants (selection_rank <= 2, where lower is better)
        - Finds optimal team assignments based on availability and preferences
        - Creates SessionMembership records for allocated Djangonauts
        """
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one session to auto-allocate teams.",
                messages.ERROR,
            )
            return

        session = queryset.first()
        allocation = allocate_teams_bounded_search(session)
        stats = apply_allocation(allocation, session)
        self.message_user(
            request,
            f"Successfully allocated {stats['created']} Djangonauts to teams. "
            f"{stats['complete_teams']} of {stats['total_teams']} teams are filled.",
            messages.SUCCESS,
        )

    def save_related(self, request, form, formsets, change) -> None:
        """Show reminder for superuser organizers to review group permissions."""
        current_organizer_count = set(
            form.instance.session_memberships.organizers().values_list("id", flat=True)
        )
        super().save_related(request, form, formsets, change)
        updated_organizer_count = set(
            form.instance.session_memberships.organizers().values_list("id", flat=True)
        )
        # If there is change to the session organizers, notify a super admin to update
        # the Session Organizers group membership.
        if (
            request.user.is_superuser
            and updated_organizer_count != current_organizer_count
        ):
            group = Group.objects.filter(name="Session Organizers").first()
            if group:
                group_url = reverse("admin:auth_group_change", args=[group.pk])
                message = mark_safe(
                    f'Review the <a href="{group_url}" target="_blank">'
                    "Session Organizers group</a> to remove those who shouldn't "
                    "have access anymore."
                )
                self.message_user(request, message, messages.INFO)

    def get_queryset(self, request):
        """Filter sessions to only those the user organizes."""
        return super().get_queryset(request).for_admin_site(request.user)


@admin.register(Team)
class TeamAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    list_display = ("name", "project", "session")
    list_filter = ("session",)

    def get_queryset(self, request):
        """Filter teams to only those in organized sessions."""
        return super().get_queryset(request).for_admin_site(request.user)


@admin.register(Waitlist)
class WaitlistAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    list_display = ("user", "session", "created_at", "notified_at")
    list_filter = ("session", "created_at", "notified_at")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "session__title",
    )
    readonly_fields = ("created_at", "notified_at")
    raw_id_fields = ("user",)
    ordering = ("-created_at",)
    actions = ["reject_waitlisted_users_action"]

    def get_queryset(self, request):
        """Filter waitlist entries to only those for organized sessions."""
        return super().get_queryset(request).for_admin_site(request.user)

    @admin.action(description="Reject waitlisted users and send rejection emails")
    def reject_waitlisted_users_action(self, request, queryset):
        """
        Reject selected users from the waitlist.

        This action will:
        1. Enqueue rejection notification emails for users not yet notified
        2. Mark them as notified (handled by the task)

        Users who have already been notified (notified_at is set) will be filtered out.
        """
        count = 0
        for waitlist_entry in queryset.not_notified():
            tasks.reject_waitlisted_user.enqueue(
                waitlist_id=waitlist_entry.pk,
            )
            count += 1
        self.message_user(
            request,
            f"Successfully queued {count} rejection email(s).",
            messages.SUCCESS,
        )


@admin.register(Testimonial)
class TestimonialAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    """Admin interface for managing testimonials."""

    list_display = (
        "title",
        "author",
        "session",
        "is_published",
        "created_at",
    )
    list_filter = ("is_published", "session", "created_at")
    search_fields = (
        "title",
        "text",
        "author__email",
        "author__first_name",
        "author__last_name",
        "session__title",
    )
    readonly_fields = ("slug", "created_at", "updated_at")
    raw_id_fields = ("author",)
    ordering = ("-created_at",)
    actions = ["publish_testimonials", "unpublish_testimonials"]

    fieldsets = (
        (None, {"fields": ("title", "text", "image", "image_description")}),
        ("Relationships", {"fields": ("session", "author")}),
        ("Status", {"fields": ("is_published",)}),
        ("Metadata", {"fields": ("slug", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        """Filter testimonials to only those for organized sessions."""
        return (
            super()
            .get_queryset(request)
            .select_related("author", "session")
            .for_admin_site(request.user)
        )

    @admin.action(description="Publish selected testimonials")
    def publish_testimonials(self, request, queryset):
        """Publish selected testimonials."""
        updated = queryset.update(is_published=True)
        self.message_user(
            request,
            f"Successfully published {updated} testimonial(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Unpublish selected testimonials")
    def unpublish_testimonials(self, request, queryset):
        """Unpublish selected testimonials."""
        updated = queryset.update(is_published=False)
        self.message_user(
            request,
            f"Successfully unpublished {updated} testimonial(s).",
            messages.SUCCESS,
        )


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0
    fields = (
        "label",
        "ordering",
        "required",
        "sensitive",
        "type_field",
        "choices",
        "help_text",
    )
    readonly_fields = ("key",)


@admin.register(Question)
class QuestionAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    model = Question
    list_display = [
        "label",
        "survey",
        "type_field",
        "required",
        "ordering",
    ]
    list_filter = ["survey", "type_field", "required"]
    search_fields = ["label", "survey__name", "key"]
    list_editable = ["ordering"]
    ordering = ["survey", "ordering"]
    fields = (
        "label",
        "ordering",
        "required",
        "sensitive",
        "type_field",
        "choices",
        "help_text",
    )
    readonly_fields = ("key",)


@admin.register(Survey)
class SurveyAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    model = Survey
    inlines = [QuestionInline]
    fields = (
        "name",
        "description",
        "editable",
        "deletable",
        "session",
    )
    readonly_fields = (
        "slug",
        "created_at",
        "updated_at",
    )
    list_display = [
        "name",
        "slug",
        "session",
        "question_count",
        "link",
        "responses",
        "latest_response",
    ]
    list_filter = ["session", "editable", "deletable", "created_at"]
    search_fields = ["name", "description", "session__title"]
    actions = ["copy_survey", "export_to_csv_with_scorers", "import_from_csv"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                annotated_responses_count=Count(
                    "usersurveyresponse__user_id", distinct=True
                ),
                annotated_latest_response=Max("usersurveyresponse__created_at"),
                annotated_question_count=Count("questions", distinct=True),
            )
            .for_admin_site(request.user)
        )

    def link(self, obj):
        url = obj.get_survey_response_url()
        return mark_safe(f'<a href="{url}">Copy to share</a>')

    @admin.display(description="Questions", ordering="annotated_question_count")
    def question_count(self, obj):
        """Display the number of questions in this survey"""
        return getattr(obj, "annotated_question_count", 0)

    def responses(self, obj):
        return getattr(obj, "annotated_responses_count", None)

    def latest_response(self, obj):
        return getattr(obj, "annotated_latest_response", None)

    def get_urls(self):
        """Add custom URLs for CSV export and import"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:survey_id>/export-csv/",
                self.admin_site.admin_view(self.export_csv_view),
                name="survey_export_csv",
            ),
            path(
                "<int:survey_id>/import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name="survey_import_csv",
            ),
        ]
        return custom_urls + urls

    def export_csv_view(self, request, survey_id):
        """Handle the CSV export form and generation"""
        survey = Survey.objects.get(pk=survey_id)

        if request.method == "POST":
            form = SurveyCSVExportForm(request.POST)
            if form.is_valid():
                return form.generate_csv(survey, request.POST)
        else:
            form = SurveyCSVExportForm()

        context = {
            "form": form,
            "survey": survey,
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "site_title": self.admin_site.site_title,
            "site_header": self.admin_site.site_header,
        }
        return render(request, "admin/survey_export_csv.html", context)

    def import_csv_view(self, request, survey_id):
        """Handle the CSV import form and processing"""
        survey = Survey.objects.get(pk=survey_id)

        if request.method == "POST":
            form = SurveyCSVImportForm(request.POST, request.FILES)
            if form.is_valid():
                result = form.import_scores(survey)
                success_msg = f"Successfully updated {result['updated']} response(s)."
                self.message_user(request, success_msg, messages.SUCCESS)
                return redirect("admin:home_survey_changelist")
        else:
            form = SurveyCSVImportForm()

        context = {
            "form": form,
            "survey": survey,
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "site_title": self.admin_site.site_title,
            "site_header": self.admin_site.site_header,
        }
        return render(request, "admin/survey_import_csv.html", context)

    @admin.action(description="Export to CSV with scorers")
    def export_to_csv_with_scorers(self, request, queryset):
        """Redirect to CSV export form for selected survey"""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one survey to export.",
                messages.ERROR,
            )
            return

        survey = queryset.first()
        url = reverse("admin:survey_export_csv", args=[survey.id])
        return redirect(url)

    @admin.action(description="Import scores from CSV")
    def import_from_csv(self, request, queryset):
        """Redirect to CSV import form for selected survey"""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one survey to import.",
                messages.ERROR,
            )
            return

        survey = queryset.first()
        url = reverse("admin:survey_import_csv", args=[survey.id])
        return redirect(url)

    @admin.action(description="Copy selected surveys (with all questions)")
    def copy_survey(self, request, queryset):
        """
        Copy selected surveys along with all their questions.
        Creates new surveys with " (Copy)" appended to the name.
        """
        copied_count = 0
        for survey in queryset:
            # Get all questions before copying the survey
            questions = list(survey.questions.all())

            # Copy the survey
            survey.pk = None
            survey.id = None
            survey.name = (
                f"{survey.name} (Copied - {timezone.now().date().isoformat()})"
            )
            survey.slug = ""  # Will be auto-generated on save
            survey.session = None  # New copy not attached to any session
            survey.save()

            # Copy all questions
            for question in questions:
                question.pk = None
                question.id = None
                question.survey = survey
                question.key = ""  # Will be auto-generated on save
                question.save()

            copied_count += 1

        self.message_user(
            request,
            f"Successfully copied {copied_count} survey(s) with all their questions.",
            messages.SUCCESS,
        )


class DjangonautMembershipFilter(admin.SimpleListFilter):
    """
    Filter UserQuestionResponses by whether the user has a
    Djangonaut session membership on the survey's session.
    """

    title = "djangonaut session membership"
    parameter_name = "djangonaut_membership"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Has Djangonaut membership"),
            ("no", "No Djangonaut membership"),
        )

    def queryset(self, request, queryset):
        """
        Filter based on whether the user has a Djangonaut session membership on
        the survey's session.
        """
        membership_exists = Exists(
            SessionMembership.objects.djangonauts().filter(
                user=OuterRef("user_survey_response__user"),
                session__application_survey=OuterRef("user_survey_response__survey"),
            )
        )
        if self.value() == "yes":
            return queryset.filter(membership_exists)
        elif self.value() == "no":
            return queryset.filter(~membership_exists)
        return queryset


@admin.register(UserQuestionResponse)
class UserQuestionResponseAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    model = UserQuestionResponse
    list_filter = ["user_survey_response__survey__name", DjangonautMembershipFilter]
    list_display = [
        "survey_name",
        "question_label",
        "value",
        "user_email",
        "created_at",
    ]
    raw_id_fields = [
        "question",
        "user_survey_response",
    ]
    search_fields = [
        "question__label",
        "user_survey_response__user__email",
        "user_survey_response__user__first_name",
        "user_survey_response__user__last_name",
    ]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                annotated_survey_name=F("user_survey_response__survey__name"),
                annotated_question_label=F("question__label"),
                annotated_user_email=F("user_survey_response__user__email"),
            )
            .for_admin_site(request.user)
        )

    def survey_name(self, obj):
        return obj.annotated_survey_name

    def question_label(self, obj):
        return obj.annotated_question_label

    def user_email(self, obj):
        return obj.annotated_user_email


class UserQuestionResponseInline(admin.StackedInline):
    model = UserQuestionResponse
    readonly_fields = ["question", "value"]
    extra = 0
    can_delete = False


class WaitlistStatusFilter(admin.SimpleListFilter):
    """Filter UserSurveyResponses by waitlist status."""

    title = "waitlist status"
    parameter_name = "waitlisted"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Waitlisted"),
            ("no", "Not Waitlisted"),
        )

    def queryset(self, request, queryset):
        """Filter the queryset based on waitlist status."""
        waitlist_exists = Exists(
            Waitlist.objects.filter(
                user=OuterRef("user"),
                session__application_survey=OuterRef("survey"),
            )
        )
        if self.value() == "yes":
            return queryset.filter(waitlist_exists)
        elif self.value() == "no":
            return queryset.filter(~waitlist_exists)
        return queryset


class SelectionStatusFilter(admin.SimpleListFilter):
    """Filter UserSurveyResponses by selection status

    Limits SessionMembership to Djangonaut role.
    """

    title = "selection status"
    parameter_name = "selected"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Selected"),
            ("no", "Not Selected"),
        )

    def queryset(self, request, queryset):
        """Filter the queryset based on selection status."""
        membership_exists = Exists(
            SessionMembership.objects.djangonauts().filter(
                user=OuterRef("user"),
                session__application_survey=OuterRef("survey"),
            )
        )
        if self.value() == "yes":
            return queryset.filter(membership_exists)
        elif self.value() == "no":
            return queryset.filter(~membership_exists)
        return queryset


class SessionFilter(admin.SimpleListFilter):
    """Filter UserSurveyResponses by the Session"""

    title = "session"
    parameter_name = "session"

    def lookups(self, request, model_admin):
        """Return list of sessions that have application surveys."""
        sessions = (
            Session.objects.filter(application_survey__isnull=False)
            .order_by("-application_start_date")
            .values("id", "title")
        )
        return list(sessions)

    def queryset(self, request, queryset):
        """Filter the queryset based on selected session."""
        if self.value():
            return queryset.filter(survey__application_session__id=self.value())
        return queryset


@admin.register(UserSurveyResponseModel)
class UserSurveyResponseAdmin(DescriptiveSearchMixin, admin.ModelAdmin):
    model = UserSurveyResponseModel
    raw_id_fields = [
        "user",
        "survey",
    ]
    list_display = [
        "survey_name",
        "user_email",
        "created_at",
    ]
    list_filter = [
        SessionFilter,
        "survey__name",
        WaitlistStatusFilter,
        SelectionStatusFilter,
    ]
    search_fields = [
        "user__email",
        "user__first_name",
        "user__last_name",
    ]
    inlines = [UserQuestionResponseInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                annotated_survey_name=F("survey__name"),
                annotated_user_email=F("user__email"),
            )
            .for_admin_site(request.user)
        )

    def survey_name(self, obj):
        return obj.annotated_survey_name

    def user_email(self, obj):
        return obj.annotated_user_email
