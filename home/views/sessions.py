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


# GitHub Stats Collection View (Issue #615)

from datetime import date, timedelta
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.http import HttpResponse

from home.services.github_stats import GitHubStatsCollector
from home.services.report_formatter import ReportFormatter


@staff_member_required
def collect_stats_view(request, session_id):
    """
    Collect and display GitHub stats for Djangonauts in a session.
    Protected by staff_member_required to ensure admin-only access.

    Args:
        request: HTTP request
        session_id: ID of the session to collect stats for

    Returns:
        Rendered template with stats or form
    """
    session = get_object_or_404(Session, id=session_id)

    # Get Djangonauts with GitHub usernames
    djangonauts = session.session_memberships.djangonauts().select_related("user")
    djangonauts_with_github = [m for m in djangonauts if m.user.github_username]

    # Check if any Djangonauts have GitHub usernames
    if not djangonauts_with_github:
        messages.warning(
            request,
            f"No Djangonauts in '{session.title}' have GitHub usernames configured. "
            "Please add GitHub usernames to user profiles first.",
        )
        return redirect("admin:home_session_changelist")

    # Get GitHub usernames
    github_usernames = [m.user.github_username for m in djangonauts_with_github]

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
    else:
        # Use session dates or default to last 7 days
        if hasattr(session, "start_date") and session.start_date:
            start_date = session.start_date
        else:
            start_date = date.today() - timedelta(days=7)

        if hasattr(session, "end_date") and session.end_date:
            end_date = session.end_date
        else:
            end_date = date.today()

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
    try:
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

        # Handle download requests
        download_format = request.GET.get("download") or request.POST.get("download")
        if download_format:
            if download_format == "csv":
                content = ReportFormatter.format_csv(report)
                response = HttpResponse(content, content_type="text/csv")
                response["Content-Disposition"] = (
                    f"attachment; "
                    f'filename="djangonaut_stats_{session.id}_{start_date}_{end_date}.csv"'
                )
                return response
            elif download_format == "txt":
                content = ReportFormatter.format_text(report)
                response = HttpResponse(content, content_type="text/plain")
                response["Content-Disposition"] = (
                    f"attachment; "
                    f'filename="djangonaut_stats_{session.id}_{start_date}_{end_date}.txt"'
                )
                return response

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

    except ValueError as e:
        messages.error(request, f"Configuration error: {str(e)}")
        return redirect("admin:home_session_changelist")
    except Exception as e:
        messages.error(request, f"Error collecting stats: {str(e)}")
        return redirect("admin:home_session_changelist")
