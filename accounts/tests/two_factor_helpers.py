"""Helpers for tests that involve two-factor authentication."""

import re
import time

from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import format_hotp_value
from allauth.mfa.totp.internal.auth import generate_totp_secret
from allauth.mfa.totp.internal.auth import hotp_value
from allauth.mfa.totp.internal.auth import TOTP
from django.core import mail
from django.test import Client
from django.urls import reverse

from accounts.models import CustomUser

PASSWORD = "correct-horse-battery-staple"


def create_user(username: str = "astronaut", **kwargs) -> CustomUser:
    """Create a user with a known password and a confirmed email address."""
    kwargs.setdefault("email", f"{username}@example.com")
    user = CustomUser.objects.create_user(
        username=username, password=PASSWORD, **kwargs
    )
    user.profile.email_confirmed = True
    user.profile.save()
    return user


def current_code(secret: str) -> str:
    """The code an authenticator app holding ``secret`` shows right now."""
    return format_hotp_value(hotp_value(secret, int(time.time()) // 30))


def enable_two_factor(user: CustomUser) -> str:
    """Give the user an authenticator app and recovery codes; return its secret."""
    secret = generate_totp_secret()
    TOTP.activate(user, secret)
    RecoveryCodes.activate(user)
    return secret


def recovery_codes(user: CustomUser) -> list[str]:
    authenticator = Authenticator.objects.get(
        user=user, type=Authenticator.Type.RECOVERY_CODES
    )
    return authenticator.wrap().get_unused_codes()


def submit_password(client: Client, user: CustomUser, **extra: str):
    """Post the login form, the first step of logging in."""
    return client.post(
        reverse("login"), {"login": user.username, "password": PASSWORD, **extra}
    )


def reauthenticate(client: Client):
    """Confirm the password, as allauth asks before two-factor changes."""
    return client.post(reverse("account_reauthenticate"), {"password": PASSWORD})


def reauthenticate_by_code(client: Client) -> None:
    """Confirm who is signed in with an emailed code, as a user without a password must."""
    url = reverse("account_request_reauthentication_code")
    recipient = client.get(url).context["form"].fields["recipient"].choices[0][0]
    client.post(url, {"recipient": recipient})
    code = re.search(r"^\S+-\S+$", mail.outbox[-1].body, re.MULTILINE).group()
    client.post(reverse("account_confirm_reauthentication_code"), {"code": code})
