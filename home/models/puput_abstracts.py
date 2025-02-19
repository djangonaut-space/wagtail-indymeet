from colorful.fields import RGBColorField
from django.utils.translation import gettext_lazy as _
from puput import abstracts
from wagtail.admin.panels import FieldPanel
from wagtail.admin.panels import InlinePanel
from wagtail.admin.panels import MultiFieldPanel
from wagtail.admin.panels import PageChooserPanel
from wagtail.fields import StreamField

from home.blocks import BaseStreamBlock

# Define our customizations for puput
# https://puput.readthedocs.io/en/latest/extending_blog.html


class BlogAbstract(abstracts.BlogAbstract):
    main_color = RGBColorField(_("Blog Main Color"), default="#5c0287")

    class Meta:
        abstract = True


class EntryAbstract(abstracts.EntryAbstract):
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
