from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxLengthValidator
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone
from modelcluster.models import ClusterableModel
from wagtail.snippets.models import register_snippet

from home.integrations.discord.service import DESCRIPTION_MAX, LOCATION_MAX, NAME_MAX
from home.managers import EventCalendarInviteQuerySet, EventQuerySet


@register_snippet
class Event(ClusterableModel):
    title = models.CharField(
        max_length=255,
        validators=[MaxLengthValidator(NAME_MAX)],
        help_text=f"Capped at {NAME_MAX} characters to fit Discord scheduled events.",
    )
    slug = models.SlugField(
        unique=True,
        help_text="This is used in the URL to identify the event.",
    )

    cover_image = models.ImageField(
        blank=True,
        null=True,
        help_text="Upload an event cover image. Free stock photos available at unsplash.com.",
    )
    cover_image_caption = models.CharField(
        max_length=255,
        blank=True,
        help_text="Attribution or caption for the cover image.",
    )

    start_time = models.DateTimeField(
        help_text="Changing this will change the link for the event. Use caution."
    )
    end_time = models.DateTimeField()
    description = models.TextField(
        blank=True,
        null=True,
        max_length=DESCRIPTION_MAX,
        validators=[MaxLengthValidator(DESCRIPTION_MAX)],
        help_text=f"Capped at {DESCRIPTION_MAX} characters to fit Discord scheduled events.",
    )
    is_published = models.BooleanField(
        default=False,
        help_text=(
            "Check this to make the event go live on the public calendar and "
            "detail pages, regardless of what Public is set to."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    session = models.ForeignKey(
        "Session",
        blank=True,
        null=True,
        related_name="events",
        on_delete=models.SET_NULL,
    )
    zoom_link = models.URLField(
        blank=True,
        default="",
        validators=[
            MaxLengthValidator(
                LOCATION_MAX,
                message=(
                    f"This Zoom link is over Discord's {LOCATION_MAX}-character "
                    "limit. A Discord event can't be created with a longer link, "
                    "so please shorten it."
                ),
            )
        ],
        help_text="Zoom join URL for this event. Set automatically when the event is created.",
    )
    video_link = models.URLField(
        blank=True,
        default="",
        help_text="Link to the recording (e.g. YouTube) after the event has taken place.",
    )
    is_public = models.BooleanField(
        default=False,
        help_text=(
            "Controls visibility, not whether the event is live: public events "
            "are visible to everyone, private events only to authenticated "
            "members of the linked session. For events with no session, this "
            "also decides who receives the calendar invite; session events "
            "always invite their session's members regardless of this setting."
        ),
    )
    extra_emails = ArrayField(
        models.EmailField(blank=True),
        default=list,
        blank=True,
        help_text=(
            "List of email addresses to include in calendar invites "
            "(e.g. guest speakers)."
        ),
    )

    calendar_invite_recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="home.EventCalendarInvite",
        related_name="calendar_invite_events",
        blank=True,
        help_text="Users who have been given a calendar invite for this event.",
    )
    zoom_meeting_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Zoom meeting ID, used to update the meeting if event details change.",
    )
    zoom_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The date and time the Zoom meeting was last successfully synced.",
    )
    discord_event_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Discord scheduled-event ID, used to update the event in Discord.",
    )
    discord_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The date and time the Discord event was last successfully synced.",
    )

    objects = EventQuerySet.as_manager()

    def __str__(self):
        return self.title

    class Meta:
        ordering = ("start_time",)

    @property
    def is_future(self):
        return self.start_time.date() >= timezone.now().date()

    def get_full_url(self):
        return settings.BASE_URL + self.get_absolute_url()

    def get_absolute_url(self):
        return reverse(
            "event_detail",
            kwargs={
                "year": self.start_time.year,
                "month": self.start_time.month,
                "slug": self.slug,
            },
        )

    def get_calendar_invite_users(self):
        """Return users who should receive a calendar invite for this event.

        - Session event: all accepted members of that session.
        - Public event (no session): all accepted session members.
        - Private event (no session): nobody; only extra_emails are invited.
        """
        from home.models import SessionMembership

        user_model = get_user_model()
        if self.session_id:
            memberships = SessionMembership.objects.for_session(self.session).accepted()
        elif self.is_public:
            memberships = SessionMembership.objects.accepted()
        else:
            return user_model.objects.none()
        return user_model.objects.filter(pk__in=memberships.values("user_id")).exclude(
            email=""
        )

    def get_calendar_invite_recipients(self) -> list[str]:
        """Return email addresses to receive a calendar invite for this event.

        The event's extra_emails are always included alongside the users from
        ``get_calendar_invite_users``.
        """
        # Keyed by lowercased address so an extra_email that duplicates a
        # member isn't mailed twice; the value keeps the original casing.
        recipients = {
            address.lower(): address for address in (self.extra_emails or []) if address
        }
        for address in self.get_calendar_invite_users().values_list("email", flat=True):
            recipients.setdefault(address.lower(), address)
        return sorted(recipients.values())

    def pending_calendar_invite_recipients(self) -> list[str]:
        """Return recipients who have not been emailed an invite yet.

        What the next send would mail, both for the admin to show before
        anything is queued and for the send itself to work from.
        """
        already_sent = {
            address.lower()
            for address in self.calendar_invites.sent().values_list("email", flat=True)
        }
        return [
            address
            for address in self.get_calendar_invite_recipients()
            if address.lower() not in already_sent
        ]


class EventCalendarInvite(models.Model):
    """One recipient's calendar invite for an event.

    An invite is both the intent to email someone and the record that it
    happened, which is what keeps a send per-recipient: each address is mailed
    on its own and stamped on its own, so a retry reaches nobody else and a
    later send only reaches people who have no invite yet.

    Addresses from ``Event.extra_emails`` belong to guests with no account
    here, so ``user`` is empty for those and the email address is the
    recipient of record.
    """

    event = models.ForeignKey(
        "Event",
        related_name="calendar_invites",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="event_calendar_invites",
        on_delete=models.CASCADE,
    )
    email = models.EmailField()
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The date and time this invite was successfully sent.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = EventCalendarInviteQuerySet.as_manager()

    class Meta:
        ordering = ("email",)
        constraints = [
            models.UniqueConstraint(
                "event",
                Lower("email"),
                name="home_eventcalendarinvite_event_email_unq",
            )
        ]

    def __str__(self) -> str:
        return self.email
