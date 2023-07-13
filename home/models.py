from django.utils import timezone
from django.db import models
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse


from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel

from wagtail.models import Page
from wagtail.admin.edit_handlers import FieldPanel
from wagtail.snippets.models import register_snippet
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from taggit.models import TaggedItemBase
from taggit.managers import TaggableManager

from home.forms import SignUpPage
from accounts.models import Link

from .managers import EventQuerySet


def sign_up_forms(context):
    return{
        'sign_up_forms': SignUpPage.objects.all(),
        'request': context['request'],
    }

class HomePage(Page):
    content_panels = Page.content_panels + [

    ]

    def get_context(self, request):
        context = super().get_context(request)
        events = Event.objects.visible()
        past_events = events.past()
        future_events = events.upcoming()
        show_rsvp = False
        if request.user.is_authenticated and request.user.profile.accepted_coc:
            show_rsvp = True
        context['past_events'] = past_events[:6]
        context['future_events'] = future_events[:6]
        context['show_rsvp'] = show_rsvp
        return context



class EventTag(TaggedItemBase):
    content_object = ParentalKey('Event', on_delete=models.CASCADE, related_name='tagged_events')


@register_snippet
class Event(ClusterableModel):
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
    tags = TaggableManager(through=EventTag, blank=True)
    speakers = models.ManyToManyField('accounts.CustomUser', related_name="speaker_events", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    capacity = models.IntegerField(blank=True, null=True)
    rsvped_members = models.ManyToManyField('accounts.CustomUser', related_name='rsvp_events', blank=True, null=True)
    organizers = models.ManyToManyField('accounts.CustomUser', blank=True, null=True)
    session = models.ForeignKey('Session', blank=True, null=True, related_name="events", on_delete=models.SET_NULL)

    objects = EventQuerySet.as_manager()


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

    def add_participant_email_verification(self, user):
        self.rsvped_members.add(user.id)
        if not user.email:
            return

        email_dict = {
            "event" : self,
            "user": user,
        }

        send_mail(
            recipient_list=[user.email],
            from_email=settings.DEFAULT_FROM_EMAIL,
            subject='Djangonaut Space RSVP',
            message=render_to_string(
                'email/email_rsvp.txt',
                email_dict
            ),
            html_message=render_to_string(
                'email/email_rsvp.html',
                email_dict
            )
        )


    def remove_participant_email_verification(self, user):
        self.rsvped_members.remove(user)
        if not user.email:
            return

        email_dict = {
            "event" : self,
            "user": user,
        }

        send_mail(
            recipient_list=[user.email],
            from_email=settings.DEFAULT_FROM_EMAIL,
            subject='Djangonaut Space RSVP Cancelation',
            message=render_to_string(
                'email/email_rsvp_cancel.txt',
                email_dict
            ),
            html_message=render_to_string(
                'email/email_rsvp_cancel.html',
                email_dict
            )
        )


    def get_full_url(self):
        return settings.BASE_URL + self.get_absolute_url()

    def get_absolute_url(self):
        return reverse('event_detail', kwargs={'pk': self.pk})

class Session(models.Model):
    start_date = models.DateField()
    end_date = models.DateField()
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    participants = models.ManyToManyField('accounts.CustomUser', related_name='sessions', blank=True, null=True)

    def __str__(self):
        return self.title
