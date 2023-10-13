from __future__ import annotations

from django.contrib import admin

from .models import Event
from .models import Session
from .models import SessionMembership


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
