"""
Signal handlers for managing user groups and staff status based on SessionMembership,
and for syncing users to the Buttondown newsletter.
"""

from allauth.account.models import EmailAddress
from home import constants
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_delete, post_save
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

    Fires on every save where email_confirmed is True, keeping tags and
    subscription status in sync with any profile changes.

    If the view that triggered this save set `_buttondown_ip_address` on the
    instance (e.g. account activation), it's forwarded to the sync task so a
    newly-created Buttondown subscriber records the originating request's IP.
    """
    if not buttondown_enabled() or raw or not instance.email_confirmed:
        return
    ip_address = getattr(instance, "_buttondown_ip_address", None)
    transaction.on_commit(
        lambda: sync_user_to_buttondown.enqueue(instance.user_id, ip_address=ip_address)
    )


@receiver(
    post_save,
    sender=SessionMembership,
    dispatch_uid="accounts.sync_buttondown_on_membership_save",
)
def sync_buttondown_on_membership_save(
    sender, instance: SessionMembership, raw: bool, **kwargs
) -> None:
    """
    Enqueue a Buttondown sync when a SessionMembership is saved.

    Role and session tags are derived live from accepted memberships, so any
    change to a membership (role, acceptance) needs to be reflected in Buttondown.
    """
    if not buttondown_enabled() or raw or not instance.user.profile.email_confirmed:
        return
    sync_user_to_buttondown.enqueue(instance.user_id)


@receiver(
    post_delete,
    sender=SessionMembership,
    dispatch_uid="accounts.sync_buttondown_on_membership_delete",
)
def sync_buttondown_on_membership_delete(
    sender, instance: SessionMembership, **kwargs
) -> None:
    """
    Enqueue a Buttondown sync when a SessionMembership is deleted.

    Removing a membership can drop role/session tags, so Buttondown needs
    to be resynced to reflect the user's remaining memberships.
    """
    if not buttondown_enabled() or not instance.user.profile.email_confirmed:
        return
    sync_user_to_buttondown.enqueue(instance.user_id)


@receiver(
    post_save,
    sender=UserProfile,
    dispatch_uid="accounts.mirror_email_confirmation_to_allauth",
)
def mirror_email_confirmation_to_allauth(
    sender, instance: UserProfile, created: bool, raw: bool, **kwargs
) -> None:
    """
    Copy the user's email and ``email_confirmed`` into allauth's ``EmailAddress``.

    ``UserProfile.email_confirmed`` stays the source of truth. allauth reads its
    own table to refuse two-factor setup on an unconfirmed address (so nobody
    can lock the real owner out of an account registered with their email) and
    to know where it may send a sign-in confirmation code.

    A profile's creation is skipped: it happens while the user is still being
    created, and allauth's GitHub signup expects to write the first
    ``EmailAddress`` rows itself. Every signup flow saves the profile again.
    """
    if raw or created:
        return
    user = instance.user
    email = user.email.lower()
    EmailAddress.objects.filter(
        Q(user=user) & ~Q(email__iexact=email)
        # Emails are unique per user, so another user's row is out of date.
        | ~Q(user=user) & Q(email__iexact=email)
    ).delete()
    if email:
        EmailAddress.objects.update_or_create(
            user=user,
            email__iexact=email,
            defaults={
                "email": email,
                "verified": instance.email_confirmed,
                "primary": True,
            },
        )
