from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxLengthValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from modelcluster.models import ClusterableModel
from wagtail.snippets.models import register_snippet

from home.integrations.discord.service import DESCRIPTION_MAX, LOCATION_MAX, NAME_MAX
from home.managers import EventQuerySet


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
    is_published = models.BooleanField(default=False)
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
    is_public = models.BooleanField(default=True)
    extra_emails = ArrayField(
        models.EmailField(blank=True),
        default=list,
        help_text=(
            "List of email addresses to include in calendar invites "
            "(e.g. guest speakers).",
        ),
    )

    calendar_invites_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The date and time calendar invites were successfully sent.",
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

    def get_calendar_invite_recipients(self) -> list[str]:
        """Return email addresses to receive a calendar invite for this event.

        - Session event: all members of that session who have an email address plus extra_emails.
        - Public event (no session): all users opted in to event updates plus extra_emails.
        - Private event (no session): Only extra_emails.
        """
        from home.models import SessionMembership

        recipients = self.extra_emails or []
        emails = []
        if self.session_id:
            emails = list(
                SessionMembership.objects.for_session(self.session)
                .accepted()
                .values_list("user__email", flat=True)
                .distinct()
            )
        elif self.is_public:
            emails = list(
                SessionMembership.objects.accepted()
                .values_list("user__email", flat=True)
                .distinct()
            )
        return list(set(emails + recipients))
