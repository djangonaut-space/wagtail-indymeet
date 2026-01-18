"""Session-related views."""

from datetime import date, timedelta
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from home.models import Session, SessionMembership
from home.services.github_stats import GitHubStatsCollector
from home.services.report_formatter import ReportFormatter


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

    # Get Djangonauts with GitHub usernames
    djangonauts = session.session_memberships.djangonauts().select_related(
        "user__profile"
    )
    djangonauts_with_github = [m for m in djangonauts if m.user.profile.github_username]

    # Check if any Djangonauts have GitHub usernames
    if not djangonauts_with_github:
        messages.warning(
            request,
            f"No Djangonauts in '{session.title}' have GitHub usernames configured. "
            "Please add GitHub usernames to user profiles first.",
        )
        return redirect("admin:home_session_changelist")

    # Get GitHub usernames
    github_usernames = [m.user.profile.github_username for m in djangonauts_with_github]

    # Determine date range
    if request.method == "POST":
        # Use custom date range from form
        start_date_str = request.POST.get("start_date")
        end_date_str = request.POST.get("end_date")

        try:
            start_date = date.fromisoformat(start_date_str)
            end_date = date.fromisoformat(end_date_str)
        except (ValueError, TypeError):
            messages.error(request, "Invalid date format. Please use YYYY-MM-DD.")
            return redirect(request.path)

        # Validate dates are not in the future
        today = date.today()
        if start_date > today:
            messages.error(
                request,
                f"Start date ({start_date}) cannot be in the future. Today is {today}.",
            )
            return redirect(request.path)
        if end_date > today:
            end_date = today  # Silently cap end_date to today
    else:
        # Use session dates or default to last 7 days
        today = date.today()
        if session.start_date and session.start_date <= today:
            start_date = session.start_date
        else:
            start_date = today - timedelta(days=7)

        if session.end_date:
            end_date = min(session.end_date, today)
        else:
            end_date = today

    # Check if we should collect stats or just show the form
    if request.method == "GET" and "collect" not in request.GET:
        # Show date selection form
        context = {
            "session": session,
            "djangonauts_count": len(djangonauts_with_github),
            "start_date": start_date,
            "end_date": end_date,
            "github_usernames": github_usernames,
            "opts": Session._meta,
            "has_view_permission": True,
        }
        return render(request, "admin/collect_stats_form.html", context)

    # Collect stats
    collector = GitHubStatsCollector()

    # Get repository configuration from settings
    repos = getattr(settings, "DJANGONAUT_MONITORED_REPOS", [])

    if not repos:
        messages.error(
            request,
            "No repositories configured. Please set DJANGONAUT_MONITORED_REPOS in settings.",
        )
        return redirect("admin:home_session_changelist")

    # Collect the stats
    report = collector.collect_all_stats(
        repos=repos,
        usernames=github_usernames,
        start_date=start_date,
        end_date=end_date,
    )

    # Format report as HTML
    report_html = ReportFormatter.format_html(report)

    # Success message
    messages.success(
        request,
        f"Successfully collected stats for {len(github_usernames)} Djangonauts. "
        f"Found {report.count_open_prs()} open PRs, {report.count_merged_prs()} merged PRs, "
        f"and {report.count_open_issues()} issues.",
    )

    context = {
        "session": session,
        "report": report,
        "report_html": report_html,
        "start_date": start_date,
        "end_date": end_date,
        "djangonauts_count": len(djangonauts_with_github),
        "opts": Session._meta,
        "has_view_permission": True,
    }
    return render(request, "admin/collect_stats_results.html", context)
