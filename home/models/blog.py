from django.db import models
from django.utils.cache import patch_cache_control
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from taggit.models import TaggedItemBase
from wagtail.admin.panels import FieldPanel
from wagtail.admin.panels import MultiFieldPanel
from wagtail.fields import RichTextField
from wagtail.fields import StreamField
from wagtail.models import Page

from home.blocks import BaseStreamBlock
from home.models.testimonial import Testimonial

# BLOG PUPUT IMPORTS


class HomePage(Page):
    content_panels = Page.content_panels + []

    def get_context(self, request):
        context = super().get_context(request)
        context["testimonials"] = (
            Testimonial.objects.published()
            .select_related("author", "session")
            .order_by("?")[:6]  # random order
        )
        return context

    def serve(self, request, *args, **kwargs):
        response = super().serve(request, *args, **kwargs)
        if request.user.is_authenticated:
            patch_cache_control(response, private=True)
        else:
            patch_cache_control(response, public=True, max_age=3600)
        return response


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

    def serve(self, request, *args, **kwargs):
        response = super().serve(request, *args, **kwargs)
        if request.user.is_authenticated:
            patch_cache_control(response, private=True)
        else:
            patch_cache_control(response, public=True, max_age=3600)
        return response
