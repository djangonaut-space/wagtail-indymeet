"""Scheduled Discord announcements for a session.

Organizers post the same rhythm of weekly messages into a session's
``#session-announcements`` channel every session. An ``Announcement`` is one
of those messages: it carries the copy, the calendar date it should go out,
and the approval state that gates it. Background tasks in
``home.tasks.session_announcements`` post the due ones and chase organizers
for approval on the rest.

Two cron schedules drive this:

* Announcements post **daily**, so an announcement goes out on whatever
  ``post_date`` it carries. The generated weekly announcements all land on a
  Monday, which is what produces the program's Monday cadence; organizers can
  still schedule an off-cycle announcement for any other day.
* Approval emails go out **weekly on Tuesday**. The six-day lead time in
  ``awaiting_approval`` means a Tuesday email covers exactly the following
  Monday's announcements, giving organizers most of a week to review.
"""

import datetime

from django.db import models
from django.utils import timezone

from home import constants
from home.models.base import BaseModel
from home.models.session import Session, SessionMembership

# Announcements posted more than this far in the future are not yet worth
# chasing organizers about. Six days is exactly the gap between the weekly
# Tuesday approval email and the following Monday's posts.
APPROVAL_LEAD_DAYS = 6


class AnnouncementQuerySet(models.QuerySet):
    def for_admin_site(self, user):
        """Filter to only announcements for sessions the user organizes."""
        if user.is_superuser:
            return self

        return self.filter(
            models.Exists(
                SessionMembership.objects.filter(
                    session=models.OuterRef("session"),
                    user=user,
                    role=constants.ORGANIZER,
                )
            )
        )

    def for_active_discord_sessions(self) -> "AnnouncementQuerySet":
        """Filter to announcements whose session has a live Discord channel.

        Mirrors ``SessionQuerySet.with_active_discord`` and additionally
        requires the announcements channel id, since that is where the
        message is posted.
        """
        return self.exclude(session__discord_category_id="").exclude(
            session__discord_announcements_channel_id=""
        )

    def approved(self) -> "AnnouncementQuerySet":
        """Filter to announcements cleared to post."""
        return self.filter(
            models.Q(needs_approval=False) | models.Q(approved_at__isnull=False)
        )

    def not_posted(self) -> "AnnouncementQuerySet":
        return self.filter(posted_at__isnull=True)

    def due(self) -> "AnnouncementQuerySet":
        return self.filter(post_date__lte=timezone.now().date())

    def needs_posting(self) -> "AnnouncementQuerySet":
        """Filter to announcements the scheduled job should post now."""
        return self.approved().not_posted().due()

    def awaiting_approval(self) -> "AnnouncementQuerySet":
        """Filter to unapproved announcements due within the lead time."""
        return self.filter(
            needs_approval=True,
            approved_at__isnull=True,
            posted_at__isnull=True,
            post_date__lte=timezone.now().date()
            + datetime.timedelta(days=APPROVAL_LEAD_DAYS),
        )

    def not_yet_emailed(self) -> "AnnouncementQuerySet":
        return self.filter(emailed_for_approval_at__isnull=True)


class Announcement(BaseModel):
    session = models.ForeignKey(
        Session, related_name="announcements", on_delete=models.CASCADE
    )
    post_date = models.DateField(help_text="When the announcement should be posted.")
    week_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Which number week it is in reference to the "
        "session start date. Week 1 is the official starting week. "
        "Leave blank to derive it from the post date.",
    )
    needs_approval = models.BooleanField(default=False)
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set this to approve the announcement and allow it to be "
        "posted. This does not need to be set if Needs Approval is False.",
    )
    posted_at = models.DateTimeField(
        null=True, blank=True, help_text="Set when the announcement is posted."
    )
    emailed_for_approval_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the organizers are emailed to approval "
        "the post if needs approval is set.",
    )
    message = models.TextField(
        help_text="The message that will be posted in Discord. Discord "
        "markdown is supported: **bold**, *italic*, ~~strikethrough~~, "
        "`code`, and > quotes. Replace any <placeholder> text before approving."
    )
    approval_note = models.TextField(
        blank=True,
        default="",
        help_text="These are read-only notes for organizers on "
        "what may need to be tweaked as part of the approval process.",
    )

    objects = models.Manager.from_queryset(AnnouncementQuerySet)()

    class Meta:
        ordering = ["post_date", "week_number"]

    def __str__(self) -> str:
        return f"{self.session.title} - Week {self.week_number} - {self.post_date}"

    def save(self, *args, **kwargs) -> None:
        if self.week_number is None:
            self.week_number = self.session.week_number_for(self.post_date)
        super().save(*args, **kwargs)

    @property
    def discord_content(self) -> str:
        """The message as posted, with the week header the copy assumes."""
        return f"**Week {self.week_number}**\n\n{self.message}"
