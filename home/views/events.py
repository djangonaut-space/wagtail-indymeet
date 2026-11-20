"""Event-related views."""

from typing import Any

from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from home.models import Event


class LoginRequired(Exception):
    """The visitor must log in to see this page."""


def event_calendar(request):
    """Render the event calendar view."""
    all_events = Event.objects.for_user(request.user)
    context = {
        "events": all_events,
    }
    return render(request, "home/calendar.html", context)


class EventDetailView(DetailView):
    """Display a single event."""

    model = Event
    template_name = "home/event_detail.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            return super().get(request, *args, **kwargs)
        except LoginRequired:
            return redirect_to_login(request.get_full_path())

    def get_queryset(self):
        """Events visible to the user; staff see all to preview drafts."""
        if self.request.user.is_staff:
            return Event.objects.all()
        return Event.objects.for_user(self.request.user)

    def get_object(self, queryset=None):
        """Get the event, or raise LoginRequired if logging in would show it.

        Logged in users who can't see an event get a 404 so they can't tell
        that it exists.
        """
        if queryset is None:
            queryset = self.get_queryset()
        year = self.kwargs["year"]
        month = self.kwargs["month"]
        slug = self.kwargs["slug"]
        try:
            return queryset.for_url(year, month, slug).get()
        except Event.DoesNotExist:
            # Community and session events are linked from invite emails, so anonymous
            # visitors are sent to log in rather than shown a 404.
            if (
                self.request.user.is_anonymous
                and Event.objects.requires_login().for_url(year, month, slug).exists()
            ):
                raise LoginRequired
            raise Http404


class EventListView(ListView):
    """Display a list of events."""

    model = Event
    template_name = "home/event_list.html"

    def get_context_data(self, **kwargs):
        """Add upcoming/past events to context."""
        context = super().get_context_data(**kwargs)

        events = Event.objects.for_user(self.request.user).order_by("-start_time")
        context["upcoming_events"] = events.upcoming()
        context["past_events"] = events.past()
        return context
