"""Session-related views."""

from datetime import date, timedelta
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from home.forms import CollectStatsForm
from home.models import Session, SessionMembership
from home.services.github_stats import GitHubStatsCollector


class SessionDetailView(DetailView):
    """Display a single session with application status."""

    model = Session
    template_name = "home/session/session_detail.html"

    def get_queryset(self) -> QuerySet[Session]:
        """Get sessions with user's application data."""
        return Session.objects.with_applications(user=self.request.user).select_related(
            "application_survey"
        )


class SessionListView(ListView):
    """Display a list of sessions with application status."""

    model = Session
    template_name = "home/session/session_list.html"
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
    template_name = "home/session/user_sessions.html"
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


@staff_member_required
def collect_stats_view(request: HttpRequest, session_id: int) -> HttpResponse:
    """
    Collect and display GitHub stats for Djangonauts in a session.

    Protected by staff_member_required to ensure admin-only access.
    """
    session = get_object_or_404(Session, id=session_id)

    repos = getattr(settings, "DJANGONAUT_MONITORED_REPOS", [])
    if not repos:
        messages.error(
            request,
            "No repositories configured. Please set DJANGONAUT_MONITORED_REPOS in settings.",
        )
        return redirect("admin:home_session_changelist")

    github_usernames = list(
        session.session_memberships.djangonauts()
        .filter(~Q(user__profile__github_username=""))
        .values_list("user__profile__github_username", flat=True)
        .distinct()
    )
    if not github_usernames:
        messages.warning(
            request,
            "No Djangonauts in this session have GitHub usernames configured.",
        )
        return redirect("admin:home_session_changelist")

    if request.method == "POST":
        form = CollectStatsForm(request.POST)
        if form.is_valid():
            report = GitHubStatsCollector().collect_all_stats(
                repos=repos,
                usernames=github_usernames,
                start_date=form.cleaned_data["start_date"],
                end_date=form.cleaned_data["end_date"],
            )

            messages.success(
                request,
                f"Successfully collected stats for {len(github_usernames)} Djangonauts. "
                f"Found {report.count_open_prs()} open PRs, "
                f"{report.count_merged_prs()} merged PRs, "
                f"{report.count_closed_prs()} closed PRs, "
                f"and {report.count_open_issues()} issues.",
            )

            return render(
                request,
                "admin/collect_stats_results.html",
                {
                    "session": session,
                    "report": report,
                    "opts": Session._meta,
                    "has_view_permission": True,
                },
            )
    else:
        today = date.today()
        form = CollectStatsForm(
            initial={
                "start_date": today - timedelta(days=7),
                "end_date": today,
            }
        )

    return render(
        request,
        "admin/collect_stats_form.html",
        {
            "session": session,
            "form": form,
            "github_usernames": github_usernames,
            "opts": Session._meta,
            "has_view_permission": True,
        },
    )
