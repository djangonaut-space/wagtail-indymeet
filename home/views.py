from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.generic.detail import DetailView

from .models import Event


def event_calendar(request):
    all_events = Event.objects.exclude(status=Event.PENDING)

    context = {
        "events":all_events,

    }
    return render(request,'home/calendar.html',context)


class EventDetailView(DetailView):
    model = Event

    def get_context_data(self, **kwargs):
        if self.request.GET.get('rsvp', None):
            if self.request.GET.get('rsvp') == 'true'\
                    and self.request.user.profile and \
                    self.request.user.profile.accepted_coc:
                self.object.rsvped_members.add(self.request.user)
            elif self.request.GET.get('rsvp') == 'false':
                self.object.rsvped_members.remove(self.request.user)
        return super().get_context_data(**kwargs)
