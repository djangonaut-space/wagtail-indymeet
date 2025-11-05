from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def send(email_template, recipient_list, context=None, from_email=None):
    if settings.ENVIRONMENT != "production":
        # When sending emails in a non-production environment, only
        # allow them to be sent to people approved testing emails.
        recipient_list = [
            recipient
            for recipient in recipient_list
            if recipient in settings.ALLOWED_EMAILS_FOR_TESTING
        ]
        if not recipient_list:
            return

    email_context = context.copy()
    # Strip the newline character that our formatter is likely to add in.
    subject = render_to_string(f"email/{email_template}/subject.txt").strip()
    if settings.ENVIRONMENT != "production":
        subject = f"[{settings.ENVIRONMENT}] " + subject
    text = render_to_string(f"email/{email_template}/body.txt", email_context)
    html = render_to_string(f"email/{email_template}/body.html", email_context)
    send_mail(
        recipient_list=recipient_list,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        subject=subject,
        message=text,
        html_message=html,
    )
