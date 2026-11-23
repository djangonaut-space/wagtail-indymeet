"""Middleware for the accounts app."""

from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import redirect

from . import two_factor

# Views a user without two-factor authentication can still reach once it is
# mandatory: setting it up, logging out, and background requests whose
# response the user never sees.
EXEMPT_VIEW_NAMES = frozenset(
    {
        "two_factor_setup",
        "logout",
        "admin:logout",
        "wagtailadmin_logout",
        "update_timezone",
    }
)
EXEMPT_NAMESPACES = frozenset({"djdt"})


class RequireTwoFactorMiddleware:
    """
    Make signed-in users set up two-factor authentication once it is mandatory.

    Does nothing until ``settings.TWO_FACTOR_REQUIRED_FROM`` is reached. From
    then on, a signed-in user without two-factor authentication is redirected
    to the setup page whatever they request, so the requirement also covers
    users who were already logged in when the deadline passed.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        # Only root-relative prefixes: an empty or absolute URL here must not
        # end up exempting every path.
        self.asset_prefixes = tuple(
            url
            for url in (settings.STATIC_URL, settings.MEDIA_URL)
            if url and url.startswith("/") and url != "/"
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., HttpResponse],
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        if not two_factor.is_required() or not request.user.is_authenticated:
            return None
        match = request.resolver_match
        if (
            match.view_name in EXEMPT_VIEW_NAMES
            or match.namespace in EXEMPT_NAMESPACES
            or request.path.startswith(self.asset_prefixes)
        ):
            return None
        if two_factor.has_two_factor(request.user):
            return None
        messages.info(
            request,
            "Two-factor authentication is now required for all accounts. "
            "Set it up to continue.",
        )
        return redirect("two_factor_setup")
