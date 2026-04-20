"""Session-related views."""

from datetime import date, timedelta
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from github import GithubException

from home.forms import CollectStatsForm
from home.models import Session, SessionMembership
from home.services.github_stats import Author, GitHubStatsCollector, TeamScope


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
            .enforce_djangonaut_access_control()
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


def _scope_term_for_project(project) -> str | None:
    """Build a GitHub search scope qualifier for a project's GitHub URL."""
    github_repo = project.github_repo
    if github_repo is None:
        return None
    owner, repo_name = github_repo
    if project.monitor_all_organization_repos:
        return f"org:{owner}"
    return f"repo:{owner}/{repo_name}"


def _build_team_scopes(session: Session) -> list[TeamScope]:
    """Build one ``TeamScope`` per team with a GitHub project and djangonauts.

    Teams whose project has no GitHub URL, or whose djangonauts have no
    GitHub username configured, produce no queries and are skipped.
    """
    djangonaut_members = Prefetch(
        "session_memberships",
        queryset=SessionMembership.objects.djangonauts().select_related(
            "user__profile"
        ),
        to_attr="team_djangonauts",
    )
    teams = session.teams.select_related("project").prefetch_related(djangonaut_members)

    scopes: list[TeamScope] = []
    for team in teams:
        scope_term = _scope_term_for_project(team.project)
        if scope_term is None:
            continue

        members_by_login: dict[str, Author] = {}
        for membership in team.team_djangonauts:
            github_username = membership.user.profile.github_username
            if not github_username or github_username in members_by_login:
                continue
            display_name = membership.user.get_full_name() or github_username
            members_by_login[github_username] = Author(
                github_username=github_username, name=display_name
            )

        if not members_by_login:
            continue

        scopes.append(
            TeamScope(
                scope_term=scope_term,
                members=tuple(members_by_login.values()),
                label=str(team),
            )
        )

    return scopes


def collect_stats_view(request: HttpRequest, session_id: int) -> HttpResponse:
    """
    Collect and display GitHub stats for Djangonauts in a session.

    Access is controlled by admin_site.admin_view() in SessionAdmin.get_urls().
    Additionally checks that the user is authorized for this specific session.
    """
    session = get_object_or_404(
        Session.objects.for_admin_site(request.user),
        id=session_id,
    )

    scopes = _build_team_scopes(session)
    if not scopes:
        messages.error(
            request,
            "No teams with GitHub projects and configured Djangonaut GitHub "
            "usernames were found for this session.",
        )
        return redirect("admin:home_session_changelist")

    djangonaut_count = len(
        {member.github_username for scope in scopes for member in scope.members}
    )

    if request.method == "POST":
        form = CollectStatsForm(request.POST)
        if form.is_valid():
            try:
                report = GitHubStatsCollector().collect_all_stats(
                    scopes=scopes,
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                )
            except (GithubException, ValueError) as e:
                messages.error(request, f"GitHub API error: {e}")
                return redirect("admin:home_session_changelist")

            messages.success(
                request,
                f"Successfully collected stats for {djangonaut_count} Djangonauts. "
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
            "scopes": scopes,
            "djangonaut_count": djangonaut_count,
            "opts": Session._meta,
            "has_view_permission": True,
        },
    )
