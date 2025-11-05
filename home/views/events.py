"""Event-related views."""

from django.shortcuts import render
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from home.models import Event


def event_calendar(request):
    """Render the event calendar view."""
    all_events = Event.objects.visible()
    context = {
        "events": all_events,
    }
    return render(request, "home/calendar.html", context)


class EventDetailView(DetailView):
    """Display a single event with RSVP functionality."""

    model = Event
    template_name = "home/event_detail.html"

    def get_object(self, queryset=None):
        """Get event by slug, year, and month."""
        if not queryset:
            queryset = self.get_queryset()
        slug = self.kwargs.get(self.slug_url_kwarg)
        slug_field = self.get_slug_field()
        queryset = queryset.filter(
            **{slug_field: slug},
            start_time__year=self.kwargs.get("year"),
            start_time__month=self.kwargs.get("month"),
        )
        return queryset.get()

    def get_context_data(self, **kwargs):
        """Handle RSVP actions in context preparation."""
        if self.request.GET.get("rsvp", None):
            if (
                self.request.GET.get("rsvp") == "true"
                and self.request.user.profile
                and self.request.user.profile.accepted_coc
                and self.request.user not in self.object.rsvped_members.all()
            ):
                self.object.add_participant_email_verification(self.request.user)
            elif (
                self.request.GET.get("rsvp") == "false"
                and self.request.user in self.object.rsvped_members.all()
            ):
                self.object.remove_participant_email_verification(self.request.user)
        return super().get_context_data(**kwargs)


class EventListView(ListView):
    """Display a list of events with filtering by tag."""

    model = Event
    template_name = "home/event_list.html"

    def get_context_data(self, **kwargs):
        """Add upcoming/past events and tags to context."""
        context = super().get_context_data(**kwargs)

        events = Event.objects.visible().order_by("-start_time")

        tag = self.request.GET.get("tag")
        if tag:
            events = events.filter(tags__name=tag)

        context["upcoming_events"] = events.upcoming()
        context["past_events"] = events.past()
        context["tags"] = self.get_event_tags()
        context["current_tag"] = tag
        return context

    def get_event_tags(self):
        """Get all unique tags from visible events."""
        tags = []
        events = Event.objects.visible().prefetch_related("tags")
        for event in events:
            tags += [tag.name for tag in event.tags.all()]
        tags = sorted(set(tags))
        return tags
