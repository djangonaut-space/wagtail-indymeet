import logging

from django.contrib.auth import get_user_model
from django_tasks import task

from home.integrations.buttondown.service import buttondown_enabled, buttondown_service

logger = logging.getLogger(__name__)

User = get_user_model()


@task()
def sync_user_to_buttondown(user_id: int) -> None:
    """
    Sync a single user's newsletter subscription state to Buttondown.

    Safely handles missing credentials, deleted users, and API failures.
    """
    if not buttondown_enabled():
        logger.warning(
            "Buttondown API key not configured; skipping sync for user %s", user_id
        )
        return

    try:
        user = User.objects.select_related("profile", "buttondown_account").get(
            pk=user_id
        )
    except User.DoesNotExist:
        logger.warning("User %s no longer exists; skipping Buttondown sync", user_id)
        return

    try:
        buttondown_service.sync_user(user)
    except Exception:
        logger.exception("Failed to sync user %s to Buttondown", user_id)


@task()
def remove_user_from_buttondown(buttondown_identifier: str) -> None:
    """
    Remove a subscriber from Buttondown by their stored UUID.

    Accepts the identifier directly (not user_id) because the user may already
    be deleted from the database when this task runs.
    """
    if not buttondown_enabled():
        logger.warning(
            "Buttondown API key not configured; skipping removal of %s",
            buttondown_identifier,
        )
        return

    try:
        buttondown_service.remove_user(buttondown_identifier)
    except Exception:
        logger.exception(
            "Failed to remove Buttondown subscriber %s", buttondown_identifier
        )
