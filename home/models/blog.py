from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from puput.abstracts import EntryAbstract
from taggit.models import TaggedItemBase
from wagtail.admin.panels import FieldPanel
from wagtail.admin.panels import MultiFieldPanel
from wagtail.admin.panels import InlinePanel
from wagtail.admin.panels import PageChooserPanel
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail import blocks
from wagtail.fields import RichTextField
from wagtail.fields import StreamField
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Page

from home import blocks as blog_blocks
from home.blocks import BaseStreamBlock
from home.models.event import Event

# BLOG PUPUT IMPORTS


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


class BlogAbstract(EntryAbstract):
    body = StreamField(
        BaseStreamBlock(),
        verbose_name="StreamField Body",
        use_json_field=True,
        null=True,
    )

    content_panels = [
        MultiFieldPanel(
            [
                FieldPanel("title", classname="title"),
                FieldPanel("header_image"),
                FieldPanel("body", classname="full"),
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
    body = RichTextField(blank=True, null=True)
    tags = ClusterTaggableManager(through=GeneralTag, blank=True)
    date = models.DateTimeField("Post Date")
    content = StreamField(
        BaseStreamBlock(),
        verbose_name="StreamField Body",
        blank=True,
        null=True,
        use_json_field=True,
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
        FieldPanel("content"),
    ]
