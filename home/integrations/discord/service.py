import logging
import re
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from home.integrations.discord.client import DiscordClient
from home.models import DiscordRole

logger = logging.getLogger(__name__)

discord_client = DiscordClient()


def discord_enabled() -> bool:
    """Check whether Discord integration is configured."""
    return all(
        [
            getattr(settings, "DISCORD_BOT_TOKEN", ""),
            getattr(settings, "DISCORD_GUILD_ID", ""),
        ]
    )


# Discord scheduled events of entity_type=EXTERNAL require an explicit end time.
# 1-hour duration by convention — most events are ~1 hour and event.end_time
# is unreliable in practice.
EVENT_DURATION = timedelta(hours=1)

# Discord's documented field-length caps for scheduled events.
# https://docs.discord.com/developers/resources/guild-scheduled-event
NAME_MAX = 100
DESCRIPTION_MAX = 1000
LOCATION_MAX = 100

# Discord's documented cap on message content length.
# https://docs.discord.com/developers/resources/message#create-message
MESSAGE_CONTENT_MAX = 2000


def _prepare_fields(event) -> tuple[str, str, str]:
    """Return the event's (name, description, location) for a Discord event.

    Title and description are capped to Discord's limits at the Event model
    level (NAME_MAX / DESCRIPTION_MAX). The location holds the Zoom link,
    where truncation would produce a broken URL,so an over-long link raises.
    """
    if len(event.zoom_link) > LOCATION_MAX:
        raise ValueError(
            f"Zoom link for event {event.pk} is {len(event.zoom_link)} characters, "
            f"over Discord's {LOCATION_MAX}-character location limit. Truncating it "
            "would break the link; shorten the Zoom link before syncing to Discord."
        )

    return event.title, event.description or "", event.zoom_link


def create_event(event) -> str:
    """Create a Discord scheduled event for an Event. Returns the Discord event ID."""
    name, description, location = _prepare_fields(event)
    data = discord_client.create_scheduled_event(
        guild_id=settings.DISCORD_GUILD_ID,
        name=name,
        description=description,
        location=location,
        start_time=event.start_time,
        end_time=event.start_time + EVENT_DURATION,
    )
    return str(data["id"])


def update_event(event) -> None:
    """Update the Discord scheduled event to match the current Event fields."""
    name, description, location = _prepare_fields(event)
    discord_client.modify_scheduled_event(
        guild_id=settings.DISCORD_GUILD_ID,
        event_id=event.discord_event_id,
        payload={
            "name": name,
            "description": description,
            "entity_metadata": {"location": location},
            "scheduled_start_time": event.start_time.isoformat(),
            "scheduled_end_time": (event.start_time + EVENT_DURATION).isoformat(),
        },
    )


class DiscordMessageTooLong(ValueError):
    pass


def create_message(
    *, channel: str, message: str, mention_role_ids: list[str] | None = None
) -> dict:
    """Post a message to a Discord channel. Returns the created message as JSON.

    ``mention_role_ids`` is the exhaustive list of roles the message is
    allowed to ping. Everything else Discord would otherwise parse out of the
    content — ``@everyone``, ``@here``, individual users — is suppressed, so
    copy nobody vetted for mentions can't notify the whole server.
    """
    if len(message) > MESSAGE_CONTENT_MAX:
        raise DiscordMessageTooLong(
            f"Message is {len(message)} characters, over Discord's "
            f"{MESSAGE_CONTENT_MAX}-character content limit."
        )
    return discord_client.create_message(
        channel_id=channel,
        content=message,
        allowed_mentions={"parse": [], "roles": list(mention_role_ids or [])},
    )


# An "@" that starts a mention: not part of a word (which would make it an
# email address) and not already following another "@". The name that follows
# must not run into a further word character, so "@Captainsville" is not a
# ping for the "Captains" role.
_MENTION_PREFIX = r"(?<![\w@])@("
_MENTION_SUFFIX = r")(?!\w)"

# The DiscordRole mirror rarely changes (only when sync_discord_roles runs),
# but resolve_role_mentions is called once per announcement row in the admin
# list and once per scheduled post, so querying it every time is an N+1.
# The signal below clears the cache whenever a role is synced, renamed, or
# removed, so it never serves stale data within this process.


@lru_cache(maxsize=1)
def _cached_roles() -> dict[str, DiscordRole]:
    """The DiscordRole mirror, keyed by casefolded name."""
    return {role.name.casefold(): role for role in DiscordRole.objects.all()}


@receiver([post_save, post_delete], sender=DiscordRole)
def _invalidate_role_mention_cache(**kwargs) -> None:
    _cached_roles.cache_clear()


def resolve_role_mentions(content: str) -> tuple[str, list[DiscordRole]]:
    """Rewrite every known ``@Role`` in ``content`` as a Discord role mention.

    This allows a mention to work as the API requires the ID, not the role name.
    Only ``@names`` that match a mirrored role are rewritten. Anything else is
    left exactly as typed, so an unknown handle, a channel reference and
    ``CoC@djangonaut.space`` all still post as the text an organizer wrote.

    Args:
        content: The message as an organizer wrote it.

    Returns:
        The rewritten message, and the roles it mentions in the order they
        first appear. Callers pass those to Discord as the allow-list of what
        the message may actually ping.
    """
    roles = _cached_roles()
    if not roles:
        return content, []

    # Longest name first so "@Session Organizers" wins over a "Session" role
    # instead of matching the short one and leaving " Organizers" dangling.
    names = sorted(roles, key=len, reverse=True)
    pattern = re.compile(
        _MENTION_PREFIX + "|".join(re.escape(name) for name in names) + _MENTION_SUFFIX,
        re.IGNORECASE,
    )
    # Keyed by id and insertion-ordered: a role mentioned twice is listed once.
    mentioned: dict[str, DiscordRole] = {}

    def replace(match: re.Match) -> str:
        role = roles[match.group(1).casefold()]
        mentioned[role.discord_id] = role
        return role.mention

    return pattern.sub(replace, content), list(mentioned.values())
