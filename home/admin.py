from django.contrib import admin

from .models import Event, Category

class EventAdmin(admin.ModelAdmin):
    model = Event

class CategoryAdmin(admin.ModelAdmin):
    model = Category


admin.site.register(Event, EventAdmin)
admin.site.register(Category, CategoryAdmin)
