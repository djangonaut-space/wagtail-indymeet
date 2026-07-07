"""
Shared settings for the Discord session setup/teardown test modules.

Every module in this package tests against the stubbed Discord API in
``home.tests.discord.stubs``, so the matching credentials are applied
automatically instead of repeating ``override_settings`` per class.
"""

import pytest

from home.tests.discord.stubs import BOT_ROLE_ID, GUILD_ID


@pytest.fixture(autouse=True)
def discord_settings(settings):
    settings.DISCORD_BOT_TOKEN = "bot-token"
    settings.DISCORD_GUILD_ID = GUILD_ID
    settings.DISCORD_BOT_ROLE_ID = BOT_ROLE_ID
    settings.BASE_URL = "https://example.com"
