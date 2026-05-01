"""
Signal handlers for managing user groups and staff status based on SessionMembership,
and for syncing users to the Buttondown newsletter.
"""

from home import constants
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import UserProfile
from home.integrations.buttondown.service import buttondown_enabled
from home.tasks.sync_buttondown import sync_user_to_buttondown
from home.models.session import SessionMembership


@receiver(
    post_save,
    sender=SessionMembership,
    dispatch_uid="accounts.manage_organizer_group_on_save",
)
def manage_organizer_group_on_save(
    sender, instance: SessionMembership, created: bool, **kwargs
) -> None:
    """
    Grant staff access and group membership when organizer role is assigned.

    Note: This only handles additions of organizer memberships. Role changes FROM
    organizer to another role require manual group removal via admin.
    """
    if instance.role == constants.ORGANIZER and not instance.user.is_superuser:
        if not instance.session.is_current_or_upcoming():
            return

        user = instance.user

        if not user.is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])

        group, _ = Group.objects.get_or_create(name="Session Organizers")
        user.groups.add(group)


@receiver(
    post_save,
    sender=UserProfile,
    dispatch_uid="accounts.sync_buttondown_on_profile_save",
)
def sync_buttondown_on_profile_save(
    sender, instance: UserProfile, created: bool, raw: bool, **kwargs
) -> None:
    """
    Enqueue a Buttondown sync when a UserProfile is saved.

    Triggers on new signups (created=True) to add the user to Buttondown,
    and on subsequent saves for users already synced (has ButtondownAccount)
    to keep tags and subscription status up to date.
    """
    if not buttondown_enabled() or raw:
        return
    sync_user_to_buttondown.enqueue(instance.user.pk)
