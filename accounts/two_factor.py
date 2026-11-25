"""
Project rules layered on top of django-allauth's two-factor authentication.

allauth owns enrolment, the login code step and recovery codes. What it has no
notion of is this project's deadline after which two-factor authentication is
mandatory, which lives here.
"""

from datetime import date

from allauth.mfa.models import Authenticator
from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone


def has_two_factor(user: AbstractBaseUser | AnonymousUser) -> bool:
    """
    Whether the user is asked for a code when logging in.

    Only an authenticator app counts, matching allauth's login step: recovery
    codes left behind on their own don't protect the account.
    """
    return is_mfa_enabled(user, [Authenticator.Type.TOTP])


def required_from() -> date | None:
    """The date two-factor authentication becomes mandatory, if one is set."""
    return settings.TWO_FACTOR_REQUIRED_FROM


def is_required() -> bool:
    """Whether the deadline for enabling two-factor authentication has passed."""
    deadline = required_from()
    return deadline is not None and timezone.localdate() >= deadline
