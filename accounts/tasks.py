"""Background task for permanent user account deletion."""

import logging

from django.contrib.auth import get_user_model
from django_tasks import task

from home import email
from home.integrations.buttondown.service import buttondown_enabled, buttondown_service

logger = logging.getLogger(__name__)

User = get_user_model()


@task()
def delete_user_account(user_id: int) -> None:
    """
    Permanently delete user account and all related data via CASCADE.

    Email confirmation is best-effort - deletion proceeds even if email fails.
    """
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        pass
    else:
        user_email = user.email
        user_name = user.get_full_name() or user.username
        if buttondown_enabled():
            buttondown_service.remove_user_for_user(user)
        user.delete()
        email.send(
            email_template="account_deleted_confirmation",
            recipient_list=[user_email],
            context={"user_name": user_name},
        )
