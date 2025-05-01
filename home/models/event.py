from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from taggit.managers import TaggableManager
from taggit.models import TaggedItemBase
from wagtail.snippets.models import register_snippet

from home.managers import EventQuerySet


class EventTag(TaggedItemBase):
    content_object = ParentalKey(
        "Event", on_delete=models.CASCADE, related_name="tagged_events"
    )


@register_snippet
class Event(ClusterableModel):
    PENDING = "Pending"
    SCHEDULED = "Scheduled"
    CANCELED = "Canceled"
    RESCHEDULED = "Rescheduled"

    EVENT_STATUS = (
        (PENDING, "Pending"),
        (SCHEDULED, "Scheduled"),
        (CANCELED, "Canceled"),
        (RESCHEDULED, "Rescheduled"),
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(help_text="This is used in the URL to identify the event.")

    cover_image = models.ImageField(blank=True, null=True)
    start_time = models.DateTimeField(
        help_text="Changing this will change the link for the event. Use caution."
    )
    end_time = models.DateTimeField()
    location = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=EVENT_STATUS, default=PENDING)
    tags = TaggableManager(through=EventTag, blank=True)
    speakers = models.ManyToManyField(
        "accounts.CustomUser", related_name="speaker_events", blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    capacity = models.IntegerField(blank=True, null=True)
    rsvped_members = models.ManyToManyField(
        "accounts.CustomUser", related_name="rsvp_events", blank=True
    )
    organizers = models.ManyToManyField("accounts.CustomUser", blank=True)
    session = models.ForeignKey(
        "Session",
        blank=True,
        null=True,
        related_name="events",
        on_delete=models.SET_NULL,
    )
    video_link = models.URLField(blank=True, null=True)
    objects = EventQuerySet.as_manager()

    def __str__(self):
        return self.title

    class Meta:
        ordering = ("start_time",)

    @property
    def is_future(self):
        return self.start_time.date() >= timezone.now().date()

    @property
    def accepting_rsvps(self):
        return self.is_future and self.status == self.SCHEDULED

    def add_participant_email_verification(self, user):
        self.rsvped_members.add(user.id)
        if not user.email:
            return

        email_dict = {
            "event": self,
            "user": user,
        }

        send_mail(
            recipient_list=[user.email],
            from_email=settings.DEFAULT_FROM_EMAIL,
            subject="Djangonaut Space RSVP",
            message=render_to_string("email/email_rsvp.txt", email_dict),
            html_message=render_to_string("email/email_rsvp.html", email_dict),
        )

    def remove_participant_email_verification(self, user):
        self.rsvped_members.remove(user)
        if not user.email:
            return

        email_dict = {
            "event": self,
            "user": user,
        }

        send_mail(
            recipient_list=[user.email],
            from_email=settings.DEFAULT_FROM_EMAIL,
            subject="Djangonaut Space RSVP Cancelation",
            message=render_to_string("email/email_rsvp_cancel.txt", email_dict),
            html_message=render_to_string("email/email_rsvp_cancel.html", email_dict),
        )

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
