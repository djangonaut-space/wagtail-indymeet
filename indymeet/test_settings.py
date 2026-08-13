from .settings import *  # noqa: F403

ZOOM_ACCOUNT_ID = ""
ZOOM_CLIENT_ID = ""
ZOOM_CLIENT_SECRET = ""

DISCORD_BOT_TOKEN = ""
DISCORD_GUILD_ID = ""

TASKS = {
    "default": {
        "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
    }
}
