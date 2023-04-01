import csv

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponse

from accounts.models import Link, CustomUser, UserProfile


class ExportCsvMixin:
    def export_as_csv(self, request, queryset):
        """
        Export all fields in a model via django admin
        """
        ignore_fields = ['password', 'token', 'bio_image']
        meta = self.model._meta
        field_names = [field.name for field in meta.fields if field.name not in ignore_fields]
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(meta)
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            exported = []
            for field in field_names:
                if hasattr(obj, field):
                   val = getattr(obj, field)
                else:
                    val = ""
                exported.append(val)
            writer.writerow(exported)
        return response

    export_as_csv.short_description = "Export Selected"

class LinksInline(admin.StackedInline):
    model = Link
    verbose_name_plural = 'links'

class CustomUserAdmin(ExportCsvMixin, BaseUserAdmin):

    model = CustomUser
    actions = ['export_as_csv']

admin.site.register(CustomUser, CustomUserAdmin)

class UserProfileAdmin(ExportCsvMixin, admin.ModelAdmin):
    inlines = (LinksInline, )
    model = UserProfile
    actions = ['export_as_csv']

admin.site.register(UserProfile, UserProfileAdmin)