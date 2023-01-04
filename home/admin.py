from django.contrib import admin

from .models import Event, Category, Speaker

class EventAdmin(admin.ModelAdmin):
    model = Event

class CategoryAdmin(admin.ModelAdmin):
    model = Category

class SpeakerAdmin(admin.ModelAdmin):
    model = Speaker


admin.site.register(Event, EventAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Speaker, SpeakerAdmin)