from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import F, Max, Count
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from .forms import SurveyCSVExportForm, SurveyCSVImportForm
from .models import Event, Project, Team
from .models import ResourceLink
from .models import Question
from .models import Session
from .models import SessionMembership
from .models import Survey
from .models import UserQuestionResponse
from .models import UserSurveyResponse as UserSurveyResponseModel
from .models import Waitlist
from .views.team_formation import (
    add_to_waitlist,
    calculate_overlap_ajax,
    team_formation_view,
)
from .views.session_notifications import (
    reject_waitlisted_user,
    send_acceptance_reminders_view,
    send_membership_acceptance_emails,
    send_session_results_view,
    send_team_welcome_emails_view,
)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    model = Event
    filter_horizontal = ("speakers", "rsvped_members", "organizers")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "url")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(ResourceLink)
class ResourceLinkAdmin(admin.ModelAdmin):
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


class SessionMembershipInline(admin.TabularInline):
    model = SessionMembership
    extra = 0


class SessionProjectInline(admin.TabularInline):
    model = Session.available_projects.through
    extra = 0
    verbose_name = "Available Project"
    verbose_name_plural = "Available Projects"


@admin.register(SessionMembership)
class SessionMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "session",
        "role",
        "team",
        "accepted",
        "acceptance_deadline",
        "created",
    )
    list_filter = ("session", "role", "accepted")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    readonly_fields = ("created", "accepted_at")
    actions = ["send_acceptance_emails_action"]

    @admin.action(description="Send acceptance emails to selected members")
    def send_acceptance_emails_action(self, request, queryset):
        """
        Send acceptance emails to selected SessionMembership records.

        This action sends acceptance notification emails to users with
        SessionMembership records, typically after team formation.
        """
        sent_count = send_membership_acceptance_emails(queryset.djangonauts())

        self.message_user(
            request,
            f"Successfully sent {sent_count} acceptance email(s).",
            messages.SUCCESS,
        )


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    inlines = [SessionMembershipInline, SessionProjectInline]
    actions = [
        "form_teams_action",
        "send_session_results_action",
        "send_acceptance_reminders_action",
        "send_team_welcome_emails_action",
    ]

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

    @admin.action(description="Form teams for this session")
    def form_teams_action(self, request, queryset):
        """Redirect to team formation interface for selected session"""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one session to form teams.",
                messages.ERROR,
            )
            return

        session = queryset.first()
        url = reverse("admin:session_form_teams", args=[session.id])
        return redirect(url)

    @admin.action(description="Send session result notifications")
    def send_session_results_action(self, request, queryset):
        """Redirect to send session results interface for selected session"""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one session to send results.",
                messages.ERROR,
            )
            return

        session = queryset.first()
        url = reverse("admin:session_send_results", args=[session.id])
        return redirect(url)

    @admin.action(description="Send acceptance reminder emails")
    def send_acceptance_reminders_action(self, request, queryset):
        """Redirect to send acceptance reminders interface for selected session"""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one session to send reminders.",
                messages.ERROR,
            )
            return

        session = queryset.first()
        url = reverse("admin:session_send_acceptance_reminders", args=[session.id])
        return redirect(url)

    @admin.action(description="Send team welcome emails")
    def send_team_welcome_emails_action(self, request, queryset):
        """Redirect to send team welcome emails interface for selected session"""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one session to send welcome emails.",
                messages.ERROR,
            )
            return

        session = queryset.first()
        url = reverse("admin:session_send_team_welcome_emails", args=[session.id])
        return redirect(url)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "session")
    list_filter = ("session",)


@admin.register(Waitlist)
class WaitlistAdmin(admin.ModelAdmin):
    list_display = ("user", "session", "created_at")
    list_filter = ("session", "created_at")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "session__title",
    )
    readonly_fields = ("created_at",)
    raw_id_fields = ("user",)
    ordering = ("-created_at",)
    actions = ["reject_waitlisted_users_action"]

    @admin.action(description="Reject waitlisted users and send rejection emails")
    def reject_waitlisted_users_action(self, request, queryset):
        """
        Reject selected users from the waitlist.

        This action will:
        1. Send rejection notification emails
        2. Remove them from the waitlist
        """
        rejected_count = 0
        for waitlist_entry in queryset:
            reject_waitlisted_user(waitlist_entry)
            rejected_count += 1

        self.message_user(
            request,
            f"Successfully rejected {rejected_count} user(s) from the waitlist "
            f"and sent rejection emails.",
            messages.SUCCESS,
        )


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0
    fields = (
        "label",
        "type_field",
        "choices",
        "help_text",
        "required",
        "ordering",
    )
    readonly_fields = ("key",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
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


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
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


@admin.register(UserQuestionResponse)
class UserQuestionResponseAdmin(admin.ModelAdmin):
    model = UserQuestionResponse
    list_filter = ["user_survey_response__survey__name"]
    list_display = [
        "survey_name",
        "question_label",
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


@admin.register(UserSurveyResponseModel)
class UserSurveyResponseAdmin(admin.ModelAdmin):
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
    list_filter = ["survey__name"]
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
        )

    def survey_name(self, obj):
        return obj.annotated_survey_name

    def user_email(self, obj):
        return obj.annotated_user_email
