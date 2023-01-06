from django.contrib import admin

from .models import Event, Category, Session

class EventAdmin(admin.ModelAdmin):
    model = Event
    filter_horizontal = ('categories', 'speakers', 'rsvped_members', 'organizers')

class CategoryAdmin(admin.ModelAdmin):
    model = Category


class SessionAdmin(admin.ModelAdmin):
    model = Session
    filter_horizontal = ('participants',)


admin.site.register(Event, EventAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Session, SessionAdmin)
