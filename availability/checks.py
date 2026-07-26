from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def check_calendar_token_encryption_key(app_configs, **kwargs):
    """Fail when Google Calendar is enabled in production without a stable key.

    Without CALENDAR_TOKEN_ENCRYPTION_KEY set, settings falls back to a key
    generated fresh on every process start, silently making previously stored
    calendar credentials unreadable across deploys/restarts.
    """
    google_calendar_enabled = bool(settings.GOOGLE_OAUTH_CLIENT_ID)
    if google_calendar_enabled and not bool(settings.CALENDAR_TOKEN_ENCRYPTION_KEY):
        return [
            Error(
                "CALENDAR_TOKEN_ENCRYPTION_KEY must be set when the Google "
                "Calendar integration is enabled so that stored "
                "credentials remain readable across deploys.",
                id="availability.E001",
            )
        ]
    return []
