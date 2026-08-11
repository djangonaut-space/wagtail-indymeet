"""Keeping the local ``DiscordMember`` mirror in step with the guild."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from home.integrations.discord.service import discord_client
from home.models import DiscordMember

GUILD_MEMBER_PAGE_SIZE = 1000


@dataclass
class MemberSyncReport:
    synced: int = 0
    deactivated: int = 0
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
    """Upsert every guild member and mark absentees inactive.

    Members are matched on ``discord_id``. Leaving the server sets
    ``is_active=False`` rather than deleting the row, so a ``UserProfile``
    link survives leave/rejoin. Returns the raw Discord payloads so callers
    like teardown can reuse the fetch.
    """
    raw_members = list_all_guild_members()
    now = timezone.now()
    seen_ids: list[str] = []
    with transaction.atomic():
        for raw in raw_members:
            user = raw["user"]
            discord_id = str(user["id"])
            seen_ids.append(discord_id)
            DiscordMember.objects.update_or_create(
                discord_id=discord_id,
                defaults={
                    "username": user["username"],
                    "global_name": user.get("global_name") or "",
                    "nickname": raw.get("nick") or "",
                    "role_ids": list(raw.get("roles") or []),
                    "is_bot": bool(user.get("bot")),
                    "is_active": True,
                    "last_seen_at": now,
                },
            )
        deactivated = DiscordMember.objects.exclude(discord_id__in=seen_ids).filter(
            is_active=True
        )
        deactivated_count = deactivated.count()
        deactivated.update(is_active=False)
    return MemberSyncReport(
        synced=len(seen_ids),
        deactivated=deactivated_count,
        members=raw_members,
    )


def apply_username_links(*, dry_run: bool = False) -> LinkReport:
    """Link profiles whose legacy ``discord_username`` uniquely matches a member.

    Only links when there is exactly one active, non-bot match and the profile
    is not already linked. Ambiguous or missing matches are skipped.
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
            DiscordMember.objects.filter(
                is_active=True,
                is_bot=False,
                username__iexact=username,
            ).order_by("pk")
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
