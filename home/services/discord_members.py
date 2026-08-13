"""Keeping the local ``DiscordMember`` mirror in step with the guild."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings

from accounts.models import UserProfile
from home.integrations.discord.service import discord_client
from home.models import DiscordMember

GUILD_MEMBER_PAGE_SIZE = 1000


@dataclass
class MemberSyncReport:
    synced: int = 0
    members: list[dict] = field(default_factory=list)


@dataclass
class LinkReport:
    linked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def list_all_guild_members() -> list[dict]:
    """Fetch the full guild member list (paginated; needs GUILD_MEMBERS intent)."""
    members: list[dict] = []
    after = None
    while True:
        page = discord_client.list_guild_members(
            guild_id=settings.DISCORD_GUILD_ID,
            limit=GUILD_MEMBER_PAGE_SIZE,
            after=after,
        )
        members.extend(page)
        if len(page) < GUILD_MEMBER_PAGE_SIZE:
            return members
        after = page[-1]["user"]["id"]


def sync_discord_members() -> MemberSyncReport:
    """Upsert guild members whose mirrored fields have changed.

    Members are matched on ``discord_id``. Rows whose username, nickname, and
    roles already match the guild are skipped, so a routine hourly sync
    doesn't rewrite every row when nothing changed. Returns the raw Discord
    payloads so callers like teardown can reuse the fetch.
    """
    raw_members = list_all_guild_members()
    existing = {member.discord_id: member for member in DiscordMember.objects.all()}

    changed = []
    for raw in raw_members:
        user = raw["user"]
        discord_id = str(user["id"])
        username = user["username"]
        nickname = raw.get("nick") or ""
        role_ids = list(raw.get("roles") or [])
        current = existing.get(discord_id)
        if (
            current is not None
            and current.username == username
            and current.nickname == nickname
            and current.role_ids == role_ids
        ):
            continue
        changed.append(
            DiscordMember(
                discord_id=discord_id,
                username=username,
                nickname=nickname,
                role_ids=role_ids,
            )
        )

    if changed:
        DiscordMember.objects.bulk_create(
            changed,
            update_conflicts=True,
            update_fields=["username", "nickname", "role_ids"],
            unique_fields=["discord_id"],
        )

    return MemberSyncReport(synced=len(raw_members), members=raw_members)


def apply_username_links(*, dry_run: bool = False) -> LinkReport:
    """Link profiles whose legacy ``discord_username`` uniquely matches a member.

    Only links when there is exactly one match and the profile is not already
    linked. Ambiguous or missing matches are skipped.
    """
    report = LinkReport()
    profiles = (
        UserProfile.objects.filter(discord_member__isnull=True)
        .exclude(discord_username="")
        .select_related("user")
    )
    for profile in profiles:
        username = profile.discord_username.strip()
        matches = list(
            DiscordMember.objects.filter(username__iexact=username).order_by("pk")
        )
        label = f"{profile.user}: {username}"
        if len(matches) != 1:
            report.skipped.append(label)
            continue
        if not dry_run:
            profile.discord_member = matches[0]
            profile.save(update_fields=["discord_member"])
        report.linked.append(label)
    return report
