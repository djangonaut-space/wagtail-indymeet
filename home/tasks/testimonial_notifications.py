"""
Background tasks for sending testimonial-related notification emails.

These tasks handle sending notification emails to administrators when
testimonials are created or updated, allowing for review and approval.
"""

from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django_tasks import task

from home import email
from home.models import Testimonial, Session

User = get_user_model()


@task()
def send_testimonial_notification(
    testimonial_id: int,
    is_new: bool,
    old_values: dict | None = None,
) -> None:
    """
    Send a notification email to superusers about a new or updated testimonial.

    Args:
        testimonial_id: The ID of the Testimonial
        is_new: True if this is a new testimonial, False if it's an update
        old_values: Dictionary of old values for comparison (for updates only)
            Contains keys: title, text, session_id
    """
    testimonial = Testimonial.objects.select_related("author", "session").get(
        pk=testimonial_id
    )

    # Get superuser email addresses
    superuser_emails = list(
        User.objects.filter(is_superuser=True, is_active=True).values_list(
            "email", flat=True
        )
    )

    if not superuser_emails:
        return

    # Build admin URL for the testimonial
    admin_url = settings.BASE_URL + reverse(
        "admin:home_testimonial_change", args=[testimonial_id]
    )

    context = {
        "testimonial": testimonial,
        "author": testimonial.author,
        "session": testimonial.session,
        "is_new": is_new,
        "admin_url": admin_url,
        "cta_link": admin_url,
    }

    # Add diff information for updates
    if not is_new and old_values:
        changes = []
        if old_values.get("title") != testimonial.title:
            changes.append(
                {
                    "field": "Title",
                    "old": old_values["title"],
                    "new": testimonial.title,
                }
            )
        if old_values.get("text") != testimonial.text:
            changes.append(
                {
                    "field": "Text",
                    "old": old_values["text"],
                    "new": testimonial.text,
                }
            )
        if old_values.get("session_id") != testimonial.session_id:
            # Get old session name if it was changed
            old_session = Session.objects.filter(pk=old_values["session_id"]).first()
            changes.append(
                {
                    "field": "Session",
                    "old": old_session.title if old_session else "Unknown",
                    "new": testimonial.session.title,
                }
            )
        context["changes"] = changes

    email.send(
        email_template="testimonial_notification",
        recipient_list=superuser_emails,
        context=context,
    )
