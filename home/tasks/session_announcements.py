"""Background tasks that post session announcements and chase their approval."""

from crontask import cron
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django_tasks import task

from home import email
from home.integrations.discord.service import create_message, resolve_role_mentions
from home.models import Announcement


@cron("0 11,14,17,20 * * *")
@task()
def schedule_pending_announcements() -> None:
    """Enqueue a post for every announcement that is due and approved."""
    announcement_ids = (
        Announcement.objects.needs_posting()
        .for_active_discord_sessions()
        .values_list("id", flat=True)
    )
    for announcement_id in announcement_ids:
        post_announcement.enqueue(announcement_id=announcement_id)


@task()
def post_announcement(announcement_id: int) -> None:
    """Post a single announcement to its session's Discord announcements channel.

    Deliberately does not check ``post_date``: the scheduled fan-out has
    already applied that filter, and the admin action needs to be able to post
    ahead of schedule. The ``not_posted`` lock is what keeps this idempotent.
    """
    with transaction.atomic():
        announcement = (
            Announcement.objects.approved()
            .not_posted()
            .select_for_update()
            .select_related("session")
            .filter(pk=announcement_id)
            .first()
        )
        if announcement is None:
            return
        content, roles = resolve_role_mentions(announcement.discord_content)
        create_message(
            channel=announcement.session.discord_announcements_channel_id,
            message=content,
            mention_role_ids=[role.discord_id for role in roles],
        )
        announcement.posted_at = timezone.now()
        announcement.save(update_fields=["posted_at", "updated_at"])


@cron("0 11,14,17,20 * * Tue")
@task()
def schedule_approval_emails() -> None:
    """Enqueue an approval email for every announcement still awaiting one."""
    announcement_ids = (
        Announcement.objects.awaiting_approval()
        .not_yet_emailed()
        .for_active_discord_sessions()
        .values_list("id", flat=True)
    )
    for announcement_id in announcement_ids:
        email_organizers_for_announcement.enqueue(announcement_id=announcement_id)


@task()
def email_organizers_for_announcement(announcement_id: int) -> None:
    """Email a session's organizers that an announcement needs approval."""
    with transaction.atomic():
        announcement = (
            Announcement.objects.awaiting_approval()
            .not_yet_emailed()
            .select_for_update()
            .select_related("session")
            .filter(pk=announcement_id)
            .first()
        )
        if announcement is None:
            return
        session = announcement.session
        organizer_emails = list(
            session.session_memberships.organizers().values_list(
                "user__email", flat=True
            )
        )
        cta_link = settings.BASE_URL + reverse(
            "admin:home_announcement_change", args=[announcement.id]
        )
        email.send(
            from_email=settings.SESSIONS_FROM_EMAIL,
            email_template="announcement_needs_approval",
            recipient_list=organizer_emails,
            context={
                "session": session,
                "announcement": announcement,
                "cta_link": cta_link,
            },
        )
        announcement.emailed_for_approval_at = timezone.now()
        announcement.save(update_fields=["emailed_for_approval_at", "updated_at"])
