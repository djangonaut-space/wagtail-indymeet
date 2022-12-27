import csv

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponse

from accounts.models import Link

# from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser

class ExportCsvMixin:
    def export_as_csv(self, request, queryset):
        """
        Export all fields in a model via django admin
        """
        ignore_fields = ['password', 'token']
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
    verbose_name_plural = 'link'

class CustomUserAdmin(ExportCsvMixin, BaseUserAdmin):

    model = CustomUser
    list_display = BaseUserAdmin.list_display + ('is_active', 'member_role')
    actions = ['export_as_csv']
    inlines = (LinksInline, )
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Custom Fields', {
            'fields': ('member_role', 'member_status', 'pronouns', 'receiving_newsletter', 'bio', 'bio_image')
        }),
    )



admin.site.register(CustomUser, CustomUserAdmin)