from __future__ import annotations

from gettext import gettext

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormMixin
from django.views.generic.list import ListView

from .forms import CreateUserSurveyResponseForm
from .models import Event, Session, Survey, UserSurveyResponse


def event_calendar(request):
    all_events = Event.objects.visible()
    context = {
        "events": all_events,
    }
    return render(request, "home/calendar.html", context)


class EventDetailView(DetailView):
    model = Event
    template_name = "home/prerelease/event_detail.html"

    def get_object(self, queryset=None):
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
    model = Event
    template_name = "home/prerelease/event_list.html"

    def get_context_data(self, **kwargs):
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
        tags = []
        events = Event.objects.visible().prefetch_related("tags")
        for event in events:
            tags += [tag.name for tag in event.tags.all()]
        tags = sorted(set(tags))
        return tags


class SessionDetailView(DetailView):
    model = Session
    template_name = "home/prerelease/session_detail.html"


class SessionListView(ListView):
    model = Session
    template_name = "home/prerelease/session_list.html"
    context_object_name = "sessions"


@method_decorator(login_required, name="dispatch")
class CreateUserSurveyResponseFormView(FormMixin, DetailView):
    model = Survey
    object = None
    form_class = CreateUserSurveyResponseForm
    success_url = reverse_lazy("session_list")
    template_name = "home/surveys/form.html"

    def dispatch(self, request, *args, **kwargs):
        survey = self.get_object()
        if UserSurveyResponse.objects.filter(survey=survey, user=request.user).exists():
            messages.warning(request, gettext("You have already submitted."))
            return redirect("session_list")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["survey"] = self.get_object()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        survey = self.get_object()
        kwargs["title_page"] = survey.name
        kwargs["sub_title_page"] = survey.description
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        self.object = self.get_object()
        if form.is_valid():
            form.save()
            messages.success(self.request, gettext("Response sent!"))
            return self.form_valid(form)
        else:
            messages.error(self.request, gettext("Something went wrong."))
            return self.form_invalid(form)
