"""A local mirror of the Discord guild's roles, so announcements can ping them.

Discord only pings on ``<@&ROLE_ID>``. Organizers write and approve
announcement copy in the admin, where a raw snowflake is neither known nor
readable, so they write ``@Djangonauts`` and the id is substituted at post
time (see ``home.integrations.discord.service``).

The mirror is guild-wide rather than per-session — the roles outlive any one
session — and is refreshed by ``home.services.discord_roles.sync_discord_roles``
as the last step of the Discord session setup action, which is when the roles
have most recently changed.
"""

from django.db import models

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
