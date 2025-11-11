"""Session-related views."""

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from home.models import Session, SessionMembership


class SessionDetailView(DetailView):
    """Display a single session with application status."""

    model = Session
    template_name = "home/session_detail.html"

    def get_queryset(self) -> QuerySet[Session]:
        """Get sessions with user's application data."""
        return Session.objects.with_applications(user=self.request.user).select_related(
            "application_survey"
        )


class SessionListView(ListView):
    """Display a list of sessions with application status."""

    model = Session
    template_name = "home/session_list.html"
    context_object_name = "sessions"

    def get_queryset(self) -> QuerySet[Session]:
        """Get sessions ordered by end date with user's application data."""
        return (
            Session.objects.with_applications(user=self.request.user)
            .select_related("application_survey")
            .order_by("-end_date")
        )


class UserSessionListView(LoginRequiredMixin, ListView):
    """Display a list of sessions the user has been a part of."""

    model = SessionMembership
    template_name = "home/user_sessions.html"
    context_object_name = "memberships"

    def get_queryset(self) -> QuerySet[SessionMembership]:
        """Get accepted memberships for the user, ordered by session end date."""
        # Get all accepted memberships for the user
        # (Djangonauts need accepted=True, other roles are automatically members)
        return (
            SessionMembership.objects.for_user(self.request.user)
            .select_related("session", "team", "team__project")
            .order_by("-session__end_date")
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add current session membership for quick access."""
        context = super().get_context_data(**kwargs)

        # Find current session membership from already-fetched memberships
        # to avoid an extra query
        current_session_membership = None
        for membership in context["memberships"]:
            if membership.session.status == "current":
                current_session_membership = membership
                break

        context["current_session_membership"] = current_session_membership

        return context
