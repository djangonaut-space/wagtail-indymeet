from gettext import gettext

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Prefetch
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormMixin
from django.views.generic.edit import ModelFormMixin
from django.views.generic.list import ListView

from .forms import CreateUserSurveyResponseForm
from .forms import UserSurveyResponseForm
from .models import Event
from .models import Session
from .models import Survey
from .models import UserQuestionResponse
from .models import UserSurveyResponse


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

    def get_queryset(self):
        return Session.objects.with_applications(user=self.request.user)


class SessionListView(ListView):
    model = Session
    template_name = "home/prerelease/session_list.html"
    context_object_name = "sessions"

    def get_queryset(self):
        return Session.objects.with_applications(user=self.request.user).order_by(
            "-end_date"
        )


class CreateUserSurveyResponseFormView(
    LoginRequiredMixin, UserPassesTestMixin, FormMixin, DetailView
):
    model = Survey
    object = None
    form_class = CreateUserSurveyResponseForm
    success_url = reverse_lazy("session_list")
    template_name = "home/surveys/form.html"

    def test_func(self):
        user = self.request.user
        return (
            user.profile.email_confirmed
            and not UserSurveyResponse.objects.filter(
                survey__slug=self.kwargs.get(self.slug_url_kwarg), user=user
            ).exists()
        )

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


class UserSurveyResponseView(
    LoginRequiredMixin, UserPassesTestMixin, ModelFormMixin, DetailView
):
    model = UserSurveyResponse
    form_class = UserSurveyResponseForm
    success_url = reverse_lazy("session_list")
    template_name = "home/surveys/form.html"

    def get_queryset(self):
        return UserSurveyResponse.objects.select_related("survey").prefetch_related(
            Prefetch(
                "userquestionresponse_set",
                queryset=UserQuestionResponse.objects.select_related("question"),
            )
        )

    def test_func(self):
        return UserSurveyResponse.objects.filter(
            user=self.request.user, id=self.kwargs.get(self.pk_url_kwarg)
        ).exists()

    def get_context_data(self, **kwargs):
        survey = self.object.survey
        kwargs["title_page"] = survey.name
        kwargs["sub_title_page"] = survey.description
        kwargs["read_only"] = True
        context_data = super().get_context_data(**kwargs)
        return context_data
