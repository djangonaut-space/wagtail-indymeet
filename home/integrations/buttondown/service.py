import logging

from django.conf import settings

from home import constants
from home.integrations.buttondown.client import ButtondownClient

logger = logging.getLogger(__name__)

SESSION_SLUG_TO_TAG: dict[str, str] = {
    "2023-pilot-session": "Session 0",
    "2024-session-1": "Session 1",
    "2024-session-2": "Session 2",
    "2024-session-3": "Session 3",
    "2025-session-4": "Session 4",
    "2025-session-5": "Session 5",
    "2026-session-6": "Session 6",
}

INTERESTED_IN_TAG_MAP: dict[str, str] = {
    constants.DJANGONAUT: "Interested Djangonaut",
    constants.CAPTAIN: "Interested Captain",
    constants.NAVIGATOR: "Interested Navigator",
    constants.ORGANIZER: "Interested Organizer",
}

ROLE_TAG_MAP: dict[str, str] = {
    constants.DJANGONAUT: "Djangonaut",
    constants.CAPTAIN: "Captain",
    constants.NAVIGATOR: "Navigator",
    constants.ORGANIZER: "Organizer",
}


def buttondown_enabled() -> bool:
    """Check whether Buttondown integration is configured."""
    return bool(getattr(settings, "BUTTONDOWN_API_KEY", ""))


def get_tags_for_user(user) -> list[str]:
    """
    Compute the complete list of Buttondown tags for a user.

    Does NOT include the "website" tag — callers add it only on first creation
    when the user did not already exist in Buttondown.
    """
    from home.models import SessionMembership

    tags: list[str] = []

    # Interested-in tags
    interested_in = getattr(user.profile, "interested_in", None) or []
    for role in interested_in:
        tag = INTERESTED_IN_TAG_MAP.get(role)
        if tag:
            tags.append(tag)

    # Accepted memberships (single query, iterated twice)
    accepted_memberships = list(
        SessionMembership.objects.filter(user=user).accepted().select_related("session")
    )

    # Session tags
    seen_session_tags: set[str] = set()
    for membership in accepted_memberships:
        session_tag = SESSION_SLUG_TO_TAG.get(membership.session.slug)
        if session_tag and session_tag not in seen_session_tags:
            tags.append(session_tag)
            seen_session_tags.add(session_tag)

    # Role tags (deduplicated, sorted for stable ordering)
    role_tags_present: set[str] = set()
    for membership in accepted_memberships:
        role_tag = ROLE_TAG_MAP.get(membership.role)
        if role_tag:
            role_tags_present.add(role_tag)
    tags.extend(sorted(role_tags_present))

    # Admin tag
    if user.is_superuser:
        tags.append("Admin")

    # "In Community" composite tag
    community_roles = {"Djangonaut", "Navigator", "Captain", "Organizer"}
    if role_tags_present & community_roles:
        tags.append("In Community")

    return tags


class ButtondownService:
    """High-level service for syncing users to Buttondown."""

    def __init__(self) -> None:
        self.client = ButtondownClient()

    def sync_user(self, user) -> None:
        """
        Sync a single user to Buttondown.

        First sync: look up by email; create or link existing subscriber.
        Subsequent sync: update tags or unsubscribe based on newsletter preference.
        """
        from accounts.models import ButtondownAccount

        try:
            bd_account = user.buttondown_account
        except ButtondownAccount.DoesNotExist:
            bd_account = None

        if bd_account is None:
            self._first_sync(user)
        else:
            self._subsequent_sync(user, bd_account)

    def _first_sync(self, user) -> None:
        """Handle first-time sync for a user with no ButtondownAccount."""
        from accounts.models import ButtondownAccount

        existing = self.client.get_subscriber_by_email(user.email)

        if existing:
            # Subscriber already existed in Buttondown — link and update tags
            subscriber_id = existing["id"]
            ButtondownAccount.objects.create(
                user=user, buttondown_identifier=subscriber_id
            )
            user.profile.receiving_newsletter = True
            user.profile.save(update_fields=["receiving_newsletter"])
            tags = get_tags_for_user(user)
            self.client.patch_subscriber(subscriber_id, {"tags": tags})
            logger.info("Linked existing Buttondown subscriber for user %s", user.pk)
        else:
            # New subscriber — add "website" tag to indicate origin
            tags = get_tags_for_user(user)
            tags.insert(0, "website")
            data = self.client.create_subscriber(user.email, tags)
            subscriber_id = data["id"]
            ButtondownAccount.objects.create(
                user=user, buttondown_identifier=subscriber_id
            )
            logger.info("Created new Buttondown subscriber for user %s", user.pk)

    def _subsequent_sync(self, user, bd_account) -> None:
        """Handle ongoing sync for a user with an existing ButtondownAccount."""
        subscriber_id = bd_account.buttondown_identifier

        if not user.profile.receiving_newsletter:
            self.client.patch_subscriber(
                subscriber_id, {"subscriber_type": "unsubscribed"}
            )
            logger.info("Unsubscribed Buttondown subscriber for user %s", user.pk)
        else:
            tags = get_tags_for_user(user)
            self.client.patch_subscriber(
                subscriber_id,
                {"tags": tags, "subscriber_type": "regular"},
            )
            logger.info("Updated Buttondown tags for user %s", user.pk)

        bd_account.save()  # Touch last_updated via auto_now

    def remove_user(self, buttondown_identifier: str) -> None:
        """Delete a subscriber from Buttondown by their stored UUID."""
        self.client.delete_subscriber(buttondown_identifier)
        logger.info("Deleted Buttondown subscriber %s", buttondown_identifier)

    def remove_user_for_user(self, user) -> None:
        """Look up a user's ButtondownAccount and delete their subscriber record."""
        from accounts.models import ButtondownAccount

        try:
            bd_identifier = user.buttondown_account.buttondown_identifier
        except ButtondownAccount.DoesNotExist:
            return
        self.remove_user(bd_identifier)


buttondown_service = ButtondownService()
