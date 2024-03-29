from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import Event
from .models import ResourceLink
from .models import Question
from .models import Session
from .models import SessionMembership
from .models import Survey
from .models import UserQuestionResponse
from .models import UserSurveyResponse


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    model = Event
    filter_horizontal = ("speakers", "rsvped_members", "organizers")


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


@admin.register(SessionMembership)
class SessionMembershipAdmin(admin.ModelAdmin):
    model = SessionMembership
    list_display = ("user", "session", "role", "created")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    model = Session
    inlines = [SessionMembershipInline]


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


@admin.register(UserQuestionResponse)
class UserQuestionResponseAdmin(admin.ModelAdmin):
    model = UserQuestionResponse


@admin.register(UserSurveyResponse)
class UserSurveyResponse(admin.ModelAdmin):
    model = UserSurveyResponse
