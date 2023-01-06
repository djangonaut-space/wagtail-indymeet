from django.utils import timezone
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
    speakers = models.ManyToManyField('accounts.CustomUser', related_name="speaker_events", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    capacity = models.IntegerField(blank=True, null=True)
    rsvped_members = models.ManyToManyField('accounts.CustomUser', related_name='rsvp_events', blank=True, null=True)
    organizers = models.ManyToManyField('accounts.CustomUser', blank=True, null=True)
    session = models.ForeignKey('Session', blank=True, null=True, related_name="events", on_delete=models.SET_NULL)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ('start_time',)

    @property
    def is_future(self):
        return self.start_time.date() >= timezone.now().date()

    @property
    def accepting_rsvps(self):
        return self.is_future and self.status == self.SCHEDULED

class Session(models.Model):
    start_date = models.DateField()
    end_date = models.DateField()
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    participants = models.ManyToManyField('accounts.CustomUser', related_name='sessions', blank=True, null=True)

    def __str__(self):
        return self.title
