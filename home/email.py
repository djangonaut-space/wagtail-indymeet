from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.urls import reverse


def send(
    email_template,
    recipient_list,
    context=None,
    from_email=None,
    attachments: list[tuple[str, bytes, str]] | None = None,
):
    """Send a templated email, optionally with file attachments.

    Args:
        email_template: Name of the email template directory under email/.
        recipient_list: List of recipient email addresses.
        context: Template context dict.
        from_email: Sender address; defaults to DEFAULT_FROM_EMAIL.
        attachments: Optional list of (filename, content, mimetype) tuples
            to attach to the email.
    """
    # Only allow emails when:
    # - in production environments
    # - in non-prod environments when the recipient is in allowed emails
    # - when the backend is sent to the console.
    if (
        settings.ENVIRONMENT != "production"
        and settings.EMAIL_BACKEND != "django.core.mail.backends.console.EmailBackend"
    ):
        # When sending emails in a non-production environment, only
        # allow them to be sent to people approved testing emails.
        recipient_list = [
            recipient
            for recipient in recipient_list
            if recipient in settings.ALLOWED_EMAILS_FOR_TESTING
        ]
        if not recipient_list:
            return

    email_context = context.copy() if context else {}
    email_context["unsubscribe_link"] = settings.BASE_URL + reverse(
        "email_subscriptions"
    )
    # Strip the newline character that our formatter is likely to add in.
    subject = render_to_string(
        f"email/{email_template}/subject.txt", email_context
    ).strip()
    if settings.ENVIRONMENT != "production":
        subject = f"[{settings.ENVIRONMENT}] " + subject
    text = render_to_string(f"email/{email_template}/body.txt", email_context)
    html = render_to_string(f"email/{email_template}/body.html", email_context)

    if attachments:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            to=recipient_list,
        )
        msg.attach_alternative(html, "text/html")
        for filename, content, mimetype in attachments:
            msg.attach(filename, content, mimetype)
        msg.send()
    else:
        send_mail(
            recipient_list=recipient_list,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            subject=subject,
            message=text,
            html_message=html,
        )
