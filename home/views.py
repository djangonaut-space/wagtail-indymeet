from django.shortcuts import render
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from .models import Event


def event_calendar(request):
    all_events = Event.objects.visible()  # type: ignore
    context = {
        "events": all_events,
    }
    return render(request, "home/calendar.html", context)


class EventDetailView(DetailView):
    model = Event

    def get_context_data(self, **kwargs):
        if self.request.GET.get("rsvp", None):
            if (
                self.request.GET.get("rsvp") == "true"
                and self.request.user.profile  # type: ignore
                and self.request.user.profile.accepted_coc  # type: ignore
                and self.request.user not in self.object.rsvped_members.all()  # type: ignore
            ):
                self.object.add_participant_email_verification(self.request.user)  # type: ignore
            elif (
                self.request.GET.get("rsvp") == "false"
                and self.request.user in self.object.rsvped_members.all() # type: ignore
            ):
                self.object.remove_participant_email_verification(self.request.user) # type: ignore
        return super().get_context_data(**kwargs)


class EventListView(ListView):
    model = Event
    paginate_by = 100  # if pagination is desired
    template_name = "home/event_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        events = Event.objects.visible().order_by("-start_time") # type: ignore

        tag = self.request.GET.get("tag")
        if tag:
            events = events.filter(tags__name=tag)

        context["events"] = events
        context["tags"] = self.get_event_tags()
        context["current_tag"] = tag
        return context

    def get_event_tags(self):
        tags = []
        events = Event.objects.visible() # type: ignore
        for event in events:
            tags += [tag.name for tag in event.tags.all()]
        tags = sorted(set(tags))
        return tags
