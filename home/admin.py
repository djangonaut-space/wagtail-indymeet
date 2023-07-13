from django.contrib import admin

from .models import Event, Session

class EventAdmin(admin.ModelAdmin):
    model = Event
    filter_horizontal = ('speakers', 'rsvped_members', 'organizers')

class SessionAdmin(admin.ModelAdmin):
    model = Session
    filter_horizontal = ('participants',)


admin.site.register(Event, EventAdmin)
admin.site.register(Session, SessionAdmin)
