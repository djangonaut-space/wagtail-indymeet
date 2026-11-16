from django import template
from django.contrib.admin.templatetags.admin_modify import submit_row

register = template.Library()


@register.inclusion_tag("admin/home/announcement/submit_line.html", takes_context=True)
def announcement_submit_row(context) -> dict:
    """Admin submit row where "Save and approve" stands in for plain "Save"."""
    row = submit_row(context)
    row["show_save"] = False
    return row
