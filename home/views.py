from django.shortcuts import render
from django.views.generic.detail import DetailView
from .models import Event


def event_calendar(request):
    all_events = Event.objects.all()

    context = {
        "events":all_events,

    }
    return render(request,'home/calendar.html',context)


class EventDetailView(DetailView):
    model = Event

