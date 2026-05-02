"""Event-related views."""

from django.shortcuts import get_object_or_404, render
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from home.models import Event


def event_calendar(request):
    """Render the event calendar view."""
    all_events = Event.objects.visible().for_user(request.user)
    context = {
        "events": all_events,
    }
    return render(request, "home/calendar.html", context)


class EventDetailView(DetailView):
    """Display a single event."""

    model = Event
    template_name = "home/event_detail.html"

    def get_queryset(self):
        """Restrict queryset to events visible to the current user."""
        return Event.objects.for_user(self.request.user)

    def get_object(self, queryset=None):
        """Get event by slug, year, and month."""
        if queryset is None:
            queryset = self.get_queryset()
        slug = self.kwargs.get(self.slug_url_kwarg)
        slug_field = self.get_slug_field()
        queryset = queryset.filter(
            **{slug_field: slug},
            start_time__year=self.kwargs.get("year"),
            start_time__month=self.kwargs.get("month"),
        )

        return get_object_or_404(queryset)


class EventListView(ListView):
    """Display a list of events."""

    model = Event
    template_name = "home/event_list.html"

    def get_context_data(self, **kwargs):
        """Add upcoming/past events to context."""
        context = super().get_context_data(**kwargs)

        events = (
            Event.objects.visible().for_user(self.request.user).order_by("-start_time")
        )
        context["upcoming_events"] = events.upcoming()
        context["past_events"] = events.past()
        return context
