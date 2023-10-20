from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from taggit.managers import TaggableManager
from taggit.models import TaggedItemBase
from wagtail.models import Page
from wagtail.snippets.models import register_snippet

from .managers import EventQuerySet
from .managers import SessionMembershipQuerySet
from home.forms import SignUpPage

# BLOG PUPUT IMPORTS
from puput.abstracts import EntryAbstract
from wagtail.core.fields import StreamField, RichTextField
from . import blocks as blog_blocks
from wagtail.core import blocks
from wagtail.images.blocks import ImageChooserBlock
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.admin.edit_handlers import (
    FieldPanel,
    InlinePanel,
    MultiFieldPanel,
    StreamFieldPanel,
    PageChooserPanel,
)
from wagtail.images.edit_handlers import ImageChooserPanel


def sign_up_forms(context):
    return {
        "sign_up_forms": SignUpPage.objects.all(),
        "request": context["request"],
    }


class HomePage(Page):
    content_panels = Page.content_panels + []

    def get_context(self, request):
        context = super().get_context(request)
        events = Event.objects.visible()
        past_events = events.past()
        future_events = events.upcoming()
        show_rsvp = False
        if request.user.is_authenticated and request.user.profile.accepted_coc:
            show_rsvp = True
        context["past_events"] = past_events[:6]
        context["future_events"] = future_events[:6]
        context["show_rsvp"] = show_rsvp
        return context


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
        "accounts.CustomUser", related_name="speaker_events", blank=True, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    capacity = models.IntegerField(blank=True, null=True)
    rsvped_members = models.ManyToManyField(
        "accounts.CustomUser", related_name="rsvp_events", blank=True, null=True
    )
    organizers = models.ManyToManyField("accounts.CustomUser", blank=True, null=True)
    session = models.ForeignKey(
        "Session",
        blank=True,
        null=True,
        related_name="events",
        on_delete=models.SET_NULL,
    )

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


class Session(models.Model):
    """Represents a mentoring session / cohort for Djangonaut Space"""

    start_date = models.DateField()
    end_date = models.DateField()
    title = models.CharField(max_length=255)
    slug = models.SlugField(
        help_text="This is used in the URL to identify the session.", unique=True
    )
    description = models.TextField(blank=True, null=True)
    # This gives you the users who are participants. If you want to find
    # the users who have a specific role, you'll need to use SessionMembership
    participants = models.ManyToManyField(
        "accounts.CustomUser",
        through="SessionMembership",
        related_name="sessions",
        blank=True,
    )
    invitation_date = models.DateField(
        help_text="This is the date when the first round of Djangonaut invitations "
        "will be sent out."
    )
    application_start_date = models.DateField(
        help_text="This is the start date for Djangonaut applications."
    )
    application_end_date = models.DateField(
        help_text="This is the end date for Djangonaut applications."
    )
    application_url = models.URLField(
        help_text="This is a URL to the Djangonaut application form. Likely Google Forms."
    )

    def __str__(self):
        return self.title

    def is_accepting_applications(self):
        """Determine if the current date is within the application window"""
        return (
            self.application_start_date
            <= timezone.now().date()
            < self.application_end_date
        )

    def get_absolute_url(self):
        return reverse("session_detail", kwargs={"slug": self.slug})


class SessionMembership(models.Model):
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "session"], name="unique_session_membership"
            )
        ]

    DJANGONAUT = "Djangonaut"
    NAVIGATOR = "Navigator"
    CAPTAIN = "Captain"

    ROLES = (
        (DJANGONAUT, _("Djangonaut")),
        (NAVIGATOR, _("Navigator")),
        (CAPTAIN, _("Mentor")),
    )
    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        "accounts.CustomUser",
        related_name="session_memberships",
        on_delete=models.CASCADE,
    )
    session = models.ForeignKey(
        Session, related_name="session_memberships", on_delete=models.CASCADE
    )
    role = models.CharField(max_length=64, choices=ROLES, default=DJANGONAUT)
    objects = models.Manager.from_queryset(SessionMembershipQuerySet)()


class BlogAbstract(EntryAbstract):
    content = StreamField(
        [
            ("heading", blog_blocks.HeadingBlock(class_name="full")),
            ("subheading", blocks.CharBlock(class_name="full")),
            ("paragraph", blocks.RichTextBlock()),
            ("html", blocks.RawHTMLBlock(icon="code", label="Raw HTML")),
            ("image", ImageChooserBlock()),
            ("text_with_heading", blog_blocks.TextWithHeadingBlock(class_name="full")),
            (
                "text_with_heading_and_right_image",
                blog_blocks.TextWithHeadingWithRightImageBlock(class_name="full"),
            ),
            (
                "text_with_heading_and_left_image",
                blog_blocks.TextWithHeadingWithLeftImageBlock(class_name="full"),
            ),
            (
                "right_image_left_text",
                blog_blocks.RightImageLeftTextBlock(class_name="full"),
            ),
            (
                "left_image_right_text",
                blog_blocks.LeftImageRightTextBlock(class_name="full"),
            ),
            (
                "left_quote_right_image",
                blog_blocks.QuoteLeftImageBlock(class_name="full"),
            ),
            ("video_embed", blog_blocks.VideoEmbed(class_name="full")),
            ("table", TableBlock(class_name="full")),
            ("code_block", blog_blocks.CodeBlock(class_name="full")),
        ],
        blank=True,
        null=True,
    )
    content_panels = [
        MultiFieldPanel(
            [
                FieldPanel("title", classname="title"),
                ImageChooserPanel("header_image"),
                FieldPanel("body", classname="full"),
                StreamFieldPanel("content"),
                FieldPanel("excerpt", classname="full"),
            ],
            heading=_("Content"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("tags"),
                InlinePanel("entry_categories", label=_("Categories")),
                InlinePanel(
                    "related_entrypage_from",
                    label=_("Related Entries"),
                    panels=[PageChooserPanel("entrypage_to")],
                ),
            ],
            heading=_("Page Metadata"),
        ),
    ]

    class Meta:
        abstract = True


class GeneralTag(TaggedItemBase):
    content_object = ParentalKey(
        "GeneralPage",
        related_name="tagged_items",
        on_delete=models.CASCADE,
    )


class GeneralPage(Page):
    intro = RichTextField(blank=True)
    body = RichTextField(blank=True)
    tags = ClusterTaggableManager(through=GeneralTag, blank=True)
    date = models.DateTimeField("Post Date")
    content = StreamField(
        [
            ("heading", blog_blocks.HeadingBlock(class_name="full")),
            ("subheading", blocks.CharBlock(class_name="full")),
            ("paragraph", blocks.RichTextBlock(class_name="full")),
            ("HTML", blocks.RawHTMLBlock(class_name="full")),
            ("image", ImageChooserBlock()),
            ("text_with_heading", blog_blocks.HeadingBlock(class_name="full")),
            (
                "text_heading_image",
                blog_blocks.TextHeadingImageBlock(class_name="full"),
            ),
            ("video_embed", blog_blocks.VideoEmbed(class_name="full")),
            ("table", TableBlock(class_name="full")),
            ("code_block", blog_blocks.CodeBlock(class_name="full")),
            ("quote_block", blog_blocks.QuoteBlock(class_name="full")),
        ],
        blank=True,
        null=True,
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("date"),
                FieldPanel("tags"),
            ],
            heading="Page Information",
        ),
        FieldPanel("intro"),
        FieldPanel("body"),
        StreamFieldPanel("content"),
    ]
