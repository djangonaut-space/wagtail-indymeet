"""Emails sent by the accounts app."""

from django.http import HttpRequest
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from home.email import send

from .models import CustomUser
from .tokens import account_activation_token


def send_user_confirmation_email(request: HttpRequest, user: CustomUser) -> None:
    """Email the user a link that confirms they own their email address."""
    invite_link = reverse(
        "activate_account",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": account_activation_token.make_token(user),
        },
    )
    email_context = {
        "cta_link": request.build_absolute_uri(invite_link),
        "name": user.get_full_name(),
    }
    send(
        email_template="email_confirmation",
        recipient_list=[user.email],
        context=email_context,
    )
