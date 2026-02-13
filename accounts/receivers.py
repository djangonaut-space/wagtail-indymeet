"""
Signal handlers for managing user groups and staff status based on SessionMembership.
"""

from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

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
    if (
        instance.role == SessionMembership.ORGANIZER
        and not instance.user.is_superuser
        and instance.session.status != "past"
    ):
        user = instance.user

        if not user.is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])

        group, _ = Group.objects.get_or_create(name="Session Organizers")
        user.groups.add(group)
