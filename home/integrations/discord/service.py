import logging
from datetime import timedelta

from django.conf import settings

from home.integrations.discord.client import DiscordClient

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


def create_message(*, channel: str, message: str) -> dict:
    """Post a message to a Discord channel. Returns the created message as JSON."""
    if len(message) > MESSAGE_CONTENT_MAX:
        raise DiscordMessageTooLong(
            f"Message is {len(message)} characters, over Discord's "
            f"{MESSAGE_CONTENT_MAX}-character content limit."
        )
    return discord_client.create_message(channel_id=channel, content=message)
