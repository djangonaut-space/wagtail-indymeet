"""Testimonial-related views."""

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import QuerySet
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from home.forms import TestimonialForm
from home.models import SessionMembership, Testimonial
from home.tasks.testimonial_notifications import send_testimonial_notification


class TestimonialListView(ListView):
    """Display a list of published testimonials with a random hero testimonial."""

    model = Testimonial
    template_name = "home/testimonials/list.html"
    context_object_name = "testimonials"

    def get_queryset(self) -> QuerySet[Testimonial]:
        """Get published testimonials with related data."""
        return (
            Testimonial.objects.published()
            .select_related("author", "session")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add hero testimonial and highlight info to context."""
        context = super().get_context_data(**kwargs)
        context["hero_testimonial"] = (
            Testimonial.objects.published().order_by("?").first()
        )

        # Check if user can create testimonials (has session memberships with available sessions)
        context["can_create_testimonial"] = False
        if self.request.user.is_authenticated:
            context["can_create_testimonial"] = SessionMembership.objects.for_user(
                self.request.user
            ).exists()
        return context


class TestimonialCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create a new testimonial."""

    model = Testimonial
    form_class = TestimonialForm
    template_name = "home/testimonials/form.html"
    success_url = reverse_lazy("profile")

    def test_func(self) -> bool:
        """Check if user has any sessions they can create testimonials for."""
        return SessionMembership.objects.for_user(self.request.user).exists()

    def handle_no_permission(self) -> HttpResponse:
        """Redirect with message if user can't create testimonials."""
        if self.request.user.is_authenticated:
            messages.info(
                self.request,
                _(
                    "You need to be a participant in a session to share a testimonial, "
                    "or you have already submitted testimonials for all your sessions."
                ),
            )
            return HttpResponseRedirect(reverse_lazy("testimonial_list"))
        return super().handle_no_permission()

    def get_form_kwargs(self) -> dict[str, Any]:
        """Pass user to form."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: TestimonialForm) -> HttpResponse:
        """Set author and trigger notification."""
        form.instance.author = self.request.user
        response = super().form_valid(form)

        send_testimonial_notification.enqueue(
            testimonial_id=self.object.pk,
            is_new=True,
        )

        messages.success(
            self.request,
            _(
                "Your testimonial has been submitted and is pending review. "
                "Thank you for sharing your experience!"
            ),
        )
        return response

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add page title to context."""
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Share Your Experience")
        context["submit_text"] = _("Submit Testimonial")
        return context


class TestimonialUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Update an existing testimonial. Only the author can edit."""

    model = Testimonial
    form_class = TestimonialForm
    template_name = "home/testimonials/form.html"
    success_url = reverse_lazy("profile")
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def test_func(self) -> bool:
        """Check if user is the author of the testimonial."""
        testimonial = self.get_object()
        return testimonial.author == self.request.user

    def get_form_kwargs(self) -> dict[str, Any]:
        """Pass user to form."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: TestimonialForm) -> HttpResponse:
        """Unpublish on edit and trigger notification."""
        # Capture old values before saving
        old_testimonial = Testimonial.objects.get(pk=self.object.pk)
        old_values = {
            "title": old_testimonial.title,
            "text": old_testimonial.text,
            "session_id": old_testimonial.session_id,
        }

        # Unpublish on edit - requires re-approval
        form.instance.is_published = False
        response = super().form_valid(form)

        # Trigger notification to admins with diff

        send_testimonial_notification.enqueue(
            testimonial_id=self.object.pk,
            is_new=False,
            old_values=old_values,
        )

        messages.success(
            self.request,
            _(
                "Your testimonial has been updated and is pending review. "
                "It will be visible again after approval."
            ),
        )
        return response

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add page title to context."""
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Edit Your Testimonial")
        context["submit_text"] = _("Update Testimonial")
        return context


class TestimonialDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """Delete a testimonial. Only the author can delete."""

    model = Testimonial
    template_name = "home/testimonials/confirm_delete.html"
    success_url = reverse_lazy("profile")
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def test_func(self) -> bool:
        """Check if user is the author of the testimonial."""
        testimonial = self.get_object()
        return testimonial.author == self.request.user

    def form_valid(self, form) -> HttpResponse:
        """Add success message on deletion."""
        messages.success(
            self.request,
            _("Your testimonial has been deleted."),
        )
        return super().form_valid(form)
