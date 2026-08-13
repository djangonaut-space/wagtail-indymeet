"""Local mirrors of the Discord guild's roles and members.

Roles (``DiscordRole``) exist so announcements can write ``@Djangonauts`` and
have the snowflake substituted at post time (see
``home.integrations.discord.service``).

Members (``DiscordMember``) exist so session setup/teardown can assign roles
by stable Discord user id instead of searching by mutable username. Both
mirrors are guild-wide and refreshed by their sync services.
"""

from django.db import models
from django.db.models import Case, F, When

from home.models.base import BaseModel


class DiscordRole(BaseModel):
    """One mentionable role on the Discord server.

    Rows are owned by the sync, not by hand: a role renamed on Discord is
    matched by ``discord_id`` and renamed here, and a role deleted there is
    deleted here so a mention can never resolve to a dead id.
    """

    name = models.CharField(
        # Discord caps role names at 100 characters.
        max_length=100,
        help_text="The role name as it appears on the Discord server. "
        "Write '@' plus this name in an announcement to ping the role.",
    )
    discord_id = models.CharField(max_length=32, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def mention(self) -> str:
        """The message text Discord renders as a ping for this role."""
        return f"<@&{self.discord_id}>"


class DiscordMember(BaseModel):
    """One member of the Discord server, keyed by stable snowflake."""

    discord_id = models.CharField(max_length=32, unique=True)
    username = models.CharField(max_length=32)
    nickname = models.CharField(max_length=64, blank=True, default="")
    role_ids = models.JSONField(default=list, blank=True)
    display_name = models.GeneratedField(
        expression=Case(
            When(nickname="", then=F("username")),
            default=F("nickname"),
        ),
        output_field=models.CharField(max_length=64),
        db_persist=True,
    )

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        if self.display_name != self.username:
            return f"{self.display_name} (@{self.username})"
        return f"@{self.username}"

    @property
    def mention(self) -> str:
        """Copy/paste text for this member: ``@username``."""
        return f"@{self.username}"
