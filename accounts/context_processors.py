"""Template context processors for the accounts app."""

from datetime import date

from django.http import HttpRequest

from . import two_factor


def two_factor_reminder(request: HttpRequest) -> dict[str, date]:
    """
    Provide the upcoming two-factor deadline to users who haven't enrolled.

    Only set while a deadline is configured and still in the future; after it
    passes, ``RequireTwoFactorMiddleware`` takes over from the reminder banner.
    """
    deadline = two_factor.required_from()
    if (
        deadline is None
        or two_factor.is_required()
        or not request.user.is_authenticated
        or two_factor.has_two_factor(request.user)
    ):
        return {}
    return {"two_factor_deadline": deadline}
