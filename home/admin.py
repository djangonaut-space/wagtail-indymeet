from __future__ import annotations

from django.contrib import admin

from .models import Event, Question, Session, SessionMembership, Survey


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    model = Event
    filter_horizontal = ("speakers", "rsvped_members", "organizers")


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
