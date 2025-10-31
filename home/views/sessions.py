"""Session-related views."""

from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from home.models import Session


class SessionDetailView(DetailView):
    """Display a single session with application status."""

    model = Session
    template_name = "home/session_detail.html"

    def get_queryset(self):
        """Get sessions with user's application data."""
        return Session.objects.with_applications(user=self.request.user)


class SessionListView(ListView):
    """Display a list of sessions with application status."""

    model = Session
    template_name = "home/session_list.html"
    context_object_name = "sessions"

    def get_queryset(self):
        """Get sessions ordered by end date with user's application data."""
        return Session.objects.with_applications(user=self.request.user).order_by(
            "-end_date"
        )
