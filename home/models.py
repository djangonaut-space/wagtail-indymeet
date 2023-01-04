from django.db import models

from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel

from wagtail.models import Page
from wagtail.snippets.edit_handlers import SnippetChooserPanel
from wagtail.admin.edit_handlers import FieldPanel, InlinePanel
from wagtail.core.models import  Orderable
from wagtail.snippets.models import register_snippet

from home.forms import SignUpPage
from accounts.models import Link

def sign_up_forms(context):
    return{
        'sign_up_forms': SignUpPage.objects.all(),
        'request': context['request'],
    }

class HomePage(Page):
    content_panels = Page.content_panels + [

    ]



@register_snippet
class Speaker(ClusterableModel):
    bio = models.TextField(verbose_name='bio', blank=True, null=True)
    image = models.ImageField(blank=True, null=True)
    name = models.CharField(max_length=255)

    panels = [
        FieldPanel('name'),
        FieldPanel('image'),
        FieldPanel('bio'),
        InlinePanel('speaker_links', label='Link items'),
    ]

    def __str__(self):
        return self.name

class SpeakerLink(Orderable):
    speaker = ParentalKey("Speaker", related_name="speaker_links", on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField( max_length=255)
    url = models.URLField(max_length=255)

    panels = [
        FieldPanel('name'),
        FieldPanel('url')
    ]

class Category(models.Model):
    name = models.CharField(max_length=25)

    def __str__(self):
        return self.name

class Event(models.Model):
    PENDING = 'Pending'
    SCHEDULED = 'Scheduled'
    CANCELED = 'Canceled'
    RESCHEDULED = 'Rescheduled'

    EVENT_STATUS = (
        (PENDING, 'Pending'),
        (SCHEDULED, 'Scheduled'),
        (CANCELED, 'Canceled'),
        (RESCHEDULED, 'Rescheduled')
    )
    title = models.CharField(max_length=255)

    cover_image = models.ImageField(blank=True, null=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    location = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=EVENT_STATUS, default=PENDING)
    categories = models.ManyToManyField('Category', related_name="events", blank=True, null=True)
    speakers = models.ManyToManyField('Speaker', related_name="speaker_events", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    capacity = models.IntegerField(blank=True, null=True)
    rsvped_members = models.ManyToManyField('accounts.CustomUSer', related_name='rsvp_events', blank=True, null=True)
    organizers = models.ManyToManyField('accounts.CustomUSer', blank=True, null=True)


    def __str__(self):
        return self.title