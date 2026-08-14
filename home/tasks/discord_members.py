import logging

from crontask import cron
from django_tasks import task

from home.integrations.discord.service import discord_enabled
from home.services.discord_members import sync_discord_members

logger = logging.getLogger(__name__)


@cron("0 * * * *")
@task()
def sync_discord_members_hourly() -> None:
    """Keep the DiscordMember mirror fresh between session setup runs."""
    if not discord_enabled():
        return
    try:
        report = sync_discord_members()
    except Exception:
        logger.exception("Hourly Discord member sync failed")
        return
    logger.info("Synced %s Discord member(s)", report.synced)
