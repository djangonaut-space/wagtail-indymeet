"""Keeping the local ``DiscordRole`` mirror in step with the guild."""

from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction

from accounts.models import DiscordRole
from home.integrations.discord.service import discord_client

# Discord's catch-all role, which every guild has and which shares the guild
# id. Its literal name is "@everyone", so mirroring it would only ever match
# "@@everyone" in announcement copy — and pinging the whole server is exactly
# what the mention allow-list at post time exists to prevent.
EVERYONE_ROLE_NAME = "@everyone"


@dataclass
class RoleSyncReport:
    synced: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def sync_discord_roles() -> RoleSyncReport:
    """Replace the ``DiscordRole`` mirror with the guild's current roles.

    Roles are matched on ``discord_id``, so a rename on Discord updates the
    stored name instead of orphaning the old one. Roles that no longer exist
    on the guild are deleted, because a mention resolving to a dead id posts
    as unreadable ``<@&...>`` noise rather than a ping.

    Bot and integration roles are skipped: Discord manages them, and nobody
    is announcing anything to a bot. Duplicate names are collapsed to the
    first role seen, since mentions are resolved by name and a second role
    with the same name could never be addressed unambiguously.

    Returns:
        Which role names are now mirrored, and which were dropped.
    """
    guild_roles = discord_client.get_guild_roles(guild_id=settings.DISCORD_GUILD_ID)

    names_by_id: dict[str, str] = {}
    seen_names: set[str] = set()
    for role in guild_roles:
        name = role["name"]
        if name == EVERYONE_ROLE_NAME or role.get("managed"):
            continue
        if name.casefold() in seen_names:
            continue
        seen_names.add(name.casefold())
        names_by_id[str(role["id"])] = name

    report = RoleSyncReport(synced=sorted(names_by_id.values()))
    with transaction.atomic():
        stale = DiscordRole.objects.exclude(discord_id__in=names_by_id)
        report.removed = sorted(stale.values_list("name", flat=True))
        stale.delete()
        for discord_id, name in names_by_id.items():
            DiscordRole.objects.update_or_create(
                discord_id=discord_id, defaults={"name": name}
            )
    return report
