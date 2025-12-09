"""Survey-related views."""

from gettext import gettext
from typing import Optional

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormMixin, ModelFormMixin

from home.forms import CreateUserSurveyResponseForm, EditUserSurveyResponseForm
from home.models import Survey, UserQuestionResponse, UserSurveyResponse


class CreateUserSurveyResponseFormView(
    LoginRequiredMixin, UserPassesTestMixin, FormMixin, DetailView
):
    """View for creating a new survey response."""

    model = Survey
    object = None
    form_class = CreateUserSurveyResponseForm
    success_url = reverse_lazy("session_list")
    template_name = "home/surveys/form.html"

    def get_queryset(self):
        """Get surveys with application_session prefetched."""
        return super().get_queryset().select_related("application_session")

    def test_func(self) -> bool:
        """Verify user can submit this survey."""
        user = self.request.user
        return (
            user.profile.email_confirmed
            and not user.usersurveyresponse_set.filter(
                survey__slug=self.kwargs.get(self.slug_url_kwarg)
            ).exists()
        )

    def handle_no_permission(self) -> HttpResponse:
        """Handle permission denied with helpful message and redirect."""
        user = self.request.user
        if not user.is_authenticated:
            return super().handle_no_permission()

        if not user.profile.email_confirmed:
            messages.warning(
                self.request,
                gettext(
                    "Please confirm your email address before submitting a survey response."
                ),
            )
            return redirect(reverse("profile"))

        messages.warning(
            self.request,
            gettext("You have already submitted a response to this survey."),
        )
        return redirect(reverse("session_list"))

    def get_form_kwargs(self) -> dict:
        """Add survey and user to form kwargs."""
        kwargs = super().get_form_kwargs()
        kwargs["survey"] = self.get_object()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        """Add survey and editing flag to context."""
        kwargs["survey"] = self.get_object()
        kwargs["is_editing"] = False
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        """Handle form submission."""
        form = self.get_form()
        self.object = self.get_object()
        if form.is_valid():
            user_survey_response = form.save()
            user_survey_response.send_created_notification()
            messages.success(self.request, gettext(f"Survey successfully saved!"))
            return self.form_valid(form)
        else:
            messages.error(self.request, gettext("Something went wrong."))
            return self.form_invalid(form)


class UserSurveyResponseView(LoginRequiredMixin, DetailView):
    """View for displaying a survey response (read-only)."""

    model = UserSurveyResponse
    template_name = "home/surveys/detail.html"
    slug_field = "survey__slug"

    def get_queryset(self):
        """Get user's survey responses with prefetched data."""
        return (
            super()
            .get_queryset()
            .filter(user=self.request.user)
            .select_related("survey__application_session")
            .prefetch_related(
                Prefetch(
                    "userquestionresponse_set",
                    queryset=UserQuestionResponse.objects.select_related("question"),
                )
            )
        )

    def get_context_data(self, **kwargs):
        """Add survey, editability, and responses to context."""
        kwargs["survey"] = self.object.survey
        kwargs["is_editable"] = self.object.is_editable()
        kwargs["responses"] = self.object.userquestionresponse_set.all()
        return super().get_context_data(**kwargs)


class EditUserSurveyResponseView(LoginRequiredMixin, ModelFormMixin, DetailView):
    """View for editing a survey response."""

    model = UserSurveyResponse
    form_class = EditUserSurveyResponseForm
    success_url = reverse_lazy("profile")
    template_name = "home/surveys/form.html"
    slug_field = "survey__slug"

    def get_queryset(self):
        """Get user's survey responses with prefetched data."""
        return (
            super()
            .get_queryset()
            .filter(user=self.request.user)
            .select_related("survey__application_session")
            .prefetch_related(
                Prefetch(
                    "userquestionresponse_set",
                    queryset=UserQuestionResponse.objects.select_related("question"),
                )
            )
        )

    def get_context_data(self, **kwargs):
        """Add survey and editing flag to context."""
        kwargs["survey"] = self.object.survey
        kwargs["is_editing"] = True
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        """Handle form submission."""
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            user_survey_response = form.save()
            user_survey_response.send_updated_notification()
            messages.success(self.request, gettext("Response updated!"))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, gettext("Something went wrong."))
            return self.form_invalid(form)
