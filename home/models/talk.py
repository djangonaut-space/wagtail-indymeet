from django.db.models import (
    CharField,
    DateField,
    TextChoices,
    TextField,
    URLField,
    UUIDField,
    CASCADE,
    ForeignKey,
    Model,
)
from django.contrib.gis.db.models import PointField
from modelcluster.models import ClusterableModel
from wagtail.snippets.models import register_snippet
from uuid import uuid4
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, HelpPanel, InlinePanel
from wagtailgeowidget.panels import GeoAddressPanel
from wagtailgeowidget.panels import LeafletPanel
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError

from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel

from wagtail.models import Orderable

from home.constants import NULL_ISLAND, SRID_WGS84


@register_snippet
class Talk(ClusterableModel):

    class TalkType(TextChoices):
        ON_SITE = "on_site", _("On-Site")
        ONLINE = "online", _("Online")

    uuid = UUIDField(default=uuid4, editable=False, unique=True)
    title = CharField(_("title"), max_length=255)
    description = TextField(
        _("description"),
        blank=True,
        help_text=_("Provide a brief summary of the talk."),
    )
    date = DateField()
    talk_type = CharField(
        _("talk Format"),
        choices=TalkType.choices,
        default=TalkType.ON_SITE,
        help_text=_("Select the format of the talk."),
        max_length=12,
    )
    event_name = CharField(
        _("event name"),
        max_length=255,
        help_text="Please provide the name of the event where the talk was held.",
    )
    video_link = URLField(_("video Link"), blank=True, default="", max_length=1024)
    address = CharField(max_length=250, blank=True, null=True)
    location = PointField(srid=SRID_WGS84, blank=True, null=True)

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("title"),
                FieldPanel("description"),
                FieldPanel("date"),
                FieldPanel("talk_type"),
                InlinePanel("speakers", heading="Speakers", min_num=1),
                FieldPanel("event_name"),
                FieldPanel("video_link"),
            ],
            _("Talk details"),
        ),
        MultiFieldPanel(
            [
                HelpPanel(
                    """
                        <strong>📍 Location Tips:</strong><br>
                        • → <strong>Type address</strong> and hit <kbd>Enter</kbd>
                        (wait auto-sets marker and save)<br>
                        • Dragging marker <strong>won't</strong> update address
                        (not recommended)<br>
                        • For no map location, leave address field empty and save.
                    """
                ),
                GeoAddressPanel("address"),
                LeafletPanel("location", address_field="address"),
            ],
            _("Geo details"),
        ),
    ]

    def __str__(self):
        return f"{self.title} - {self.event_name} - {self.date.year} - {self.get_speakers_names()}"

    def get_speakers_names(self):
        """Get comma-separated list of speaker names.

        Returns:
            str: "Jane Doe, John Smith" from all TalkSpeaker.speaker CustomUser instances

        Note:
            self.speakers.all() returns TalkSpeaker instances (not CustomUser).
            Access speaker names via s.speaker.get_full_name() or s.speaker.username.
        """
        return ", ".join(
            [
                s.speaker.get_full_name() or s.speaker.username
                for s in self.speakers.all()
            ]
        )

    def clean(self):
        super().clean()
        if self.talk_type == self.TalkType.ON_SITE and not self.address:
            raise ValidationError({"address": "Address required for on-site talks."})

        if not self.address:
            self.location = NULL_ISLAND

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TalkSpeaker(Orderable, Model):
    talk = ParentalKey("Talk", related_name="speakers")
    speaker = ForeignKey("accounts.CustomUser", on_delete=CASCADE)

    class Meta:
        unique_together = ("talk", "speaker")

    panels = [
        FieldPanel("speaker", help_text="Select a speaker"),
    ]
