from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic.edit import UpdateView

from availability.forms import UserAvailabilityForm
from availability.models import UserAvailability


class UpdateAvailabilityView(LoginRequiredMixin, UpdateView):
    """View for updating user's weekly availability."""

    form_class = UserAvailabilityForm
    template_name = "registration/update_availability.html"

    def get_object(self, queryset=None):
        """Get or create the UserAvailability object for the current user."""
        availability, created = UserAvailability.objects.get_or_create(
            user=self.request.user
        )
        return availability

    def get_success_url(self):
        messages.add_message(
            self.request,
            messages.SUCCESS,
            "Your availability has been updated successfully.",
        )
        return reverse("profile")
