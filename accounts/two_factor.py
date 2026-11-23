"""Two-factor authentication helpers built on django-otp.

A user has two-factor authentication enabled when they own a *confirmed*
``TOTPDevice`` (an authenticator app). Recovery codes live on a single
``StaticDevice`` per user and only exist alongside a confirmed TOTP device.

See ``docs/two-factor-auth.md`` for the overall design.
"""

import time
from base64 import b32encode
from dataclasses import dataclass
from datetime import date
from datetime import timedelta

import segno
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django_otp.models import Device
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_static.models import StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import CustomUser
from home import email

TOTP_DEVICE_NAME = "Authenticator app"
RECOVERY_DEVICE_NAME = "Recovery codes"
RECOVERY_CODE_COUNT = 10
# How long the secret shown on the setup page stays usable before a new one
# is generated.
PENDING_DEVICE_MAX_AGE = timedelta(hours=1)

# Values for the ``change`` context variable of the ``two_factor_changed`` email.
CHANGE_ENABLED = "enabled"
CHANGE_DISABLED = "disabled"
CHANGE_RECOVERY_CODES = "recovery_codes_regenerated"
CHANGE_RESET = "reset"

RECOVERY_TOKEN_SALT = "accounts.two_factor.recovery"
# How long an admin-issued recovery link stays valid.
RECOVERY_TOKEN_MAX_AGE = 24 * 60 * 60

PENDING_LOGIN_SESSION_KEY = "two_factor_pending_login"
# How long a user has to enter their code after their password was accepted.
PENDING_LOGIN_MAX_AGE = 10 * 60


class TwoFactorThrottled(Exception):
    """Raised when a device is refusing attempts after repeated wrong codes."""


@dataclass(frozen=True)
class PendingLogin:
    """A login whose password step succeeded but whose code step hasn't yet."""

    user: CustomUser
    backend: str
    redirect_url: str


def has_two_factor(user: CustomUser) -> bool:
    """Return whether the user has finished setting up an authenticator app."""
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def get_or_create_pending_device(user: CustomUser) -> TOTPDevice:
    """
    Return the user's unconfirmed authenticator device, creating one if needed.

    The pending device is reused across requests so the QR code stays the same
    if the user reloads the setup page or mistypes their first code. It is
    replaced once it is older than ``PENDING_DEVICE_MAX_AGE``, so a secret
    someone glimpsed on an abandoned setup page can't end up protecting the
    account later.
    """
    pending = TOTPDevice.objects.filter(user=user, confirmed=False)
    pending.exclude(created_at__gt=timezone.now() - PENDING_DEVICE_MAX_AGE).delete()
    device = pending.first()
    if device is None:
        device = TOTPDevice.objects.create(
            user=user, name=TOTP_DEVICE_NAME, confirmed=False
        )
    return device


def get_manual_entry_key(device: TOTPDevice) -> str:
    """Return the device secret as base32, for users who can't scan the QR code."""
    return b32encode(device.bin_key).decode()


def get_qr_code_data_uri(device: TOTPDevice) -> str:
    """Return the device's provisioning URL as an SVG QR code data URI."""
    return segno.make(device.config_url, error="m").svg_data_uri(scale=5, border=2)


def remaining_recovery_codes(user: CustomUser) -> int:
    """Return how many unused recovery codes the user has left."""
    return StaticToken.objects.filter(device__user=user).count()


@transaction.atomic
def generate_recovery_codes(user: CustomUser) -> list[str]:
    """Replace the user's recovery codes with a fresh set and return them."""
    device, _ = StaticDevice.objects.get_or_create(
        user=user, name=RECOVERY_DEVICE_NAME, defaults={"confirmed": True}
    )
    device.token_set.all().delete()
    codes = [StaticToken.random_token() for _ in range(RECOVERY_CODE_COUNT)]
    StaticToken.objects.bulk_create(
        StaticToken(device=device, token=code) for code in codes
    )
    return codes


@transaction.atomic
def enable_two_factor(device: TOTPDevice) -> list[str]:
    """Confirm a verified authenticator device and return new recovery codes."""
    device.confirmed = True
    device.save(update_fields=["confirmed"])
    return generate_recovery_codes(device.user)


@transaction.atomic
def disable_two_factor(user: CustomUser) -> None:
    """Remove the user's authenticator devices and recovery codes."""
    TOTPDevice.objects.filter(user=user).delete()
    StaticDevice.objects.filter(user=user).delete()


def send_two_factor_changed_email(user: CustomUser, change: str) -> None:
    """Tell the user their two-factor settings changed, in case it wasn't them."""
    email.send(
        email_template="two_factor_changed",
        recipient_list=[user.email],
        context={
            "user": user,
            "name": user.first_name or user.username,
            "change": change,
        },
    )


def set_pending_login(
    request: HttpRequest, user: CustomUser, redirect_url: str
) -> None:
    """
    Remember that the user passed the password step, without logging them in.

    ``user`` must come from ``authenticate()`` so it carries the backend that
    accepted the password; the code step needs it to finish the login.
    """
    request.session[PENDING_LOGIN_SESSION_KEY] = {
        "user_id": user.pk,
        "backend": user.backend,
        "redirect_url": redirect_url,
        "created": time.time(),
    }


def clear_pending_login(request: HttpRequest) -> None:
    request.session.pop(PENDING_LOGIN_SESSION_KEY, None)


def get_pending_login(request: HttpRequest) -> PendingLogin | None:
    """
    Return the login awaiting its code step, or ``None`` if there isn't one.

    Stale state is discarded: the password step expires after
    ``PENDING_LOGIN_MAX_AGE`` and is void if the account was deactivated or
    had two-factor authentication removed in the meantime.
    """
    data = request.session.get(PENDING_LOGIN_SESSION_KEY)
    if not data:
        return None
    user = None
    if time.time() - data["created"] <= PENDING_LOGIN_MAX_AGE:
        user = CustomUser.objects.filter(pk=data["user_id"], is_active=True).first()
    if user is None or not has_two_factor(user):
        clear_pending_login(request)
        return None
    return PendingLogin(
        user=user, backend=data["backend"], redirect_url=data["redirect_url"]
    )


def normalize_token(token: str) -> str:
    """Strip the spacing and capitalisation people add when copying codes."""
    return "".join(token.split()).lower()


@transaction.atomic
def verify_login_token(user: CustomUser, token: str) -> Device | None:
    """
    Check an authenticator or recovery code and return the device it matched.

    The code is checked against one device only, chosen by its shape, so a
    wrong guess can't use up attempts on both. Returns ``None`` for a wrong
    code and raises ``TwoFactorThrottled`` while the device is locked after
    repeated failures. A matching recovery code is consumed.
    """
    token = normalize_token(token)
    devices = TOTPDevice.objects.filter(user=user, confirmed=True)
    totp_device = devices.first()
    if totp_device is None:
        return None
    if not (token.isdigit() and len(token) == totp_device.digits):
        devices = StaticDevice.objects.filter(user=user, confirmed=True)
    # Lock the row so concurrent requests can't reuse a code or dodge throttling.
    device = devices.select_for_update().first()
    if device is None:
        return None
    allowed, _reason = device.verify_is_allowed()
    if not allowed:
        raise TwoFactorThrottled
    return device if device.verify_token(token) else None


def required_from() -> date | None:
    """Return the date two-factor authentication becomes mandatory, if any."""
    return settings.TWO_FACTOR_REQUIRED_FROM


def is_required() -> bool:
    """Return whether every user must have two-factor authentication today."""
    deadline = required_from()
    return deadline is not None and timezone.localdate() >= deadline


def make_recovery_token(user: CustomUser) -> str:
    """
    Create a signed token that lets a locked-out user reset two-factor auth.

    The token names the authenticator device it was issued for. Resetting
    deletes that device, which is what makes the token single-use. The user
    must have two-factor authentication enabled.
    """
    device = TOTPDevice.objects.filter(user=user, confirmed=True).earliest("pk")
    return signing.dumps(
        {"user_id": user.pk, "device_id": device.pk}, salt=RECOVERY_TOKEN_SALT
    )


def get_user_for_recovery_token(token: str) -> CustomUser | None:
    """Return the user a recovery token is valid for, or ``None``."""
    try:
        data = signing.loads(
            token, salt=RECOVERY_TOKEN_SALT, max_age=RECOVERY_TOKEN_MAX_AGE
        )
    except signing.BadSignature:
        return None
    device = (
        TOTPDevice.objects.filter(
            pk=data["device_id"],
            user_id=data["user_id"],
            user__is_active=True,
            confirmed=True,
        )
        .select_related("user")
        .first()
    )
    return device.user if device else None


def send_recovery_email(user: CustomUser) -> None:
    """Email the user a link for resetting their two-factor authentication."""
    path = reverse("two_factor_recover", kwargs={"token": make_recovery_token(user)})
    email.send(
        email_template="two_factor_recovery",
        recipient_list=[user.email],
        context={
            "user": user,
            "name": user.first_name or user.username,
            "cta_link": settings.BASE_URL + path,
            "valid_hours": RECOVERY_TOKEN_MAX_AGE // 3600,
        },
    )
