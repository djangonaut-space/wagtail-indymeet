import logging

from django.conf import settings
from requests import HTTPError

from accounts.models import ButtondownAccount, UserProfile
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
    return bool(settings.BUTTONDOWN_API_KEY)


def get_tags_for_user(user) -> list[str]:
    """
    Compute the complete list of Buttondown tags for a user.

    Does NOT include the "website" tag — callers add it only on first creation
    when the user did not already exist in Buttondown.
    """
    tags: list[str] = []

    # Interested-in tags
    interested_in = getattr(user.profile, "interested_in", None) or []
    for role in interested_in:
        tag = INTERESTED_IN_TAG_MAP.get(role)
        if tag:
            tags.append(tag)

    # Accepted memberships (single query, iterated twice)
    accepted_memberships = list(
        user.session_memberships.accepted().select_related("session")
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

        Determines the correct action based on whether a subscriber ID is already
        known. If not (new user or account without an ID), it looks up the subscriber
        by email and links them, or creates a new one. If the ID is known, it updates
        tags or subscription status.
        """
        try:
            bd_account = user.buttondown_account
        except ButtondownAccount.DoesNotExist:
            bd_account = None

        subscriber_id = bd_account.buttondown_identifier if bd_account else None

        try:
            if subscriber_id:
                try:
                    if not user.profile.receiving_newsletter:
                        subscriber_type = "unsubscribed"
                    else:
                        subscriber_type = "regular"
                    tags = get_tags_for_user(user)
                    self.client.patch_subscriber(
                        subscriber_id,
                        {"tags": tags, "type": subscriber_type},
                    )
                except HTTPError as exc:
                    if exc.response is not None and exc.response.status_code == 404:
                        logger.info(
                            "Missing Buttondown subscriber for user %s", user.pk
                        )
                        subscriber_id = None
                    else:
                        raise

            if not subscriber_id:
                self._resolve_and_link(user, bd_account)
                return

            bd_account.save()  # Touch last_updated via auto_now
        except Exception:
            logger.exception("Failed to sync user %s to Buttondown", user.pk)

    def _resolve_and_link(self, user, bd_account: "ButtondownAccount | None") -> None:
        """
        Resolve a subscriber ID by looking up the user's email, then link or create.

        Used when no subscriber ID is available — either because there is no
        ButtondownAccount yet, or because the account exists without an identifier.
        """
        existing = self.client.get_subscriber_by_email(user.email)

        if existing:
            subscriber_id = existing["id"]
            ButtondownAccount.objects.update_or_create(
                user=user, defaults={"buttondown_identifier": subscriber_id}
            )
            UserProfile.objects.filter(user=user).update(receiving_newsletter=True)
            tags = get_tags_for_user(user)
            self.client.patch_subscriber(
                subscriber_id, {"tags": tags, "type": "regular"}
            )
            logger.info("Linked existing Buttondown subscriber for user %s", user.pk)
        else:
            tags = get_tags_for_user(user)
            tags.insert(0, "website")
            data = self.client.create_subscriber(user.email, tags)
            subscriber_id = data["id"]
            ButtondownAccount.objects.update_or_create(
                user=user, defaults={"buttondown_identifier": subscriber_id}
            )
            logger.info("Created new Buttondown subscriber for user %s", user.pk)

    def remove_user(self, buttondown_identifier: str) -> None:
        """Delete a subscriber from Buttondown by their stored UUID."""
        try:
            self.client.delete_subscriber(buttondown_identifier)
            logger.info("Deleted Buttondown subscriber %s", buttondown_identifier)
        except Exception:
            logger.exception(
                "Failed to remove Buttondown subscriber %s", buttondown_identifier
            )

    def remove_user_for_user(self, user) -> None:
        """Look up a user's ButtondownAccount and delete their subscriber record."""
        try:
            bd_identifier = user.buttondown_account.buttondown_identifier
        except ButtondownAccount.DoesNotExist:
            return
        self.remove_user(bd_identifier)


buttondown_service = ButtondownService()
