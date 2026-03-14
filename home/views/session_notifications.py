"""
Views for sending session-related notifications.

Provides admin interfaces for:
- Sending session result notifications (accepted/waitlist/rejected)
- Sending acceptance reminder emails
- Sending team welcome emails

Email sending is handled asynchronously via background tasks.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from home import tasks
from home.forms import SendSessionResultsForm
from home.models import Session, SessionMembership, UserSurveyResponse, Waitlist


@staff_member_required
@require_http_methods(["GET", "POST"])
def send_session_results_view(request: HttpRequest, session_id: int) -> HttpResponse:
    """
    Admin view to send session result notifications.

    Sends three types of emails via background tasks:
    - Accepted: to users with SessionMembership
    - Waitlisted: to users on the Waitlist
    - Rejected: to users who applied but are neither accepted nor waitlisted
    """
    session = get_object_or_404(Session, pk=session_id)

    # Calculate counts for confirmation page
    # Only send acceptance notifications to Djangonauts, but track all accepted users
    djangonaut_memberships = (
        SessionMembership.objects.for_session(session)
        .djangonauts()
        .select_related("user", "team", "team__project")
    )

    waitlisted_entries = Waitlist.objects.filter(session=session).select_related("user")
    waitlisted_count = waitlisted_entries.count()

    applicant_responses = UserSurveyResponse.objects.filter(
        survey=session.application_survey
    ).select_related("user")
    applicant_count = applicant_responses.count()
    applicant_user_ids = set(applicant_responses.values_list("user_id", flat=True))
    # For rejection calculation, use ALL session memberships, not just Djangonauts
    accepted_user_ids = set(djangonaut_memberships.values_list("user_id", flat=True))
    accepted_count = len(accepted_user_ids)
    waitlisted_user_ids = set(waitlisted_entries.values_list("user_id", flat=True))
    rejected_user_ids = applicant_user_ids - accepted_user_ids - waitlisted_user_ids
    rejected_count = len(rejected_user_ids)

    if request.method == "POST":
        form = SendSessionResultsForm(request.POST)
        if form.is_valid():

            # Calculate acceptance deadline
            deadline_days = form.cleaned_data["deadline_days"]
            acceptance_deadline = timezone.now().date() + timedelta(days=deadline_days)

            # Bulk update acceptance deadline for Djangonaut memberships without one
            djangonaut_memberships.filter(acceptance_deadline__isnull=True).update(
                acceptance_deadline=acceptance_deadline
            )
            for membership in djangonaut_memberships:
                tasks.send_accepted_email.enqueue(
                    membership_id=membership.pk,
                )
            for waitlist_entry in waitlisted_entries:
                tasks.send_waitlisted_email.enqueue(
                    waitlist_id=waitlist_entry.pk,
                    applicant_count=applicant_count,
                    accepted_count=accepted_count,
                )
            for user_id in rejected_user_ids:
                tasks.send_rejected_email.enqueue(
                    user_id=user_id,
                    session_id=session.pk,
                    applicant_count=applicant_count,
                    accepted_count=accepted_count,
                )
            session.results_notifications_sent_at = timezone.now()
            session.save(update_fields=["results_notifications_sent_at"])

            messages.success(
                request,
                f"Successfully queued {accepted_count} accepted, "
                f"{waitlisted_count} waitlisted, and "
                f"{rejected_count} rejected notifications for '{session.title}'.",
            )
            return redirect("admin:home_session_changelist")
    else:
        form = SendSessionResultsForm()

    context = {
        "session": session,
        "form": form,
        "applicant_count": applicant_count,
        "accepted_count": accepted_count,
        "waitlisted_count": waitlisted_count,
        "rejected_count": rejected_count,
        "already_sent": session.results_notifications_sent_at is not None,
        "sent_at": session.results_notifications_sent_at,
        "opts": Session._meta,
        "site_title": "Django site admin",
        "site_header": "Django administration",
        "has_view_permission": True,
    }

    return render(request, "admin/send_session_results.html", context)


@staff_member_required
@require_http_methods(["GET", "POST"])
def send_acceptance_reminders_view(
    request: HttpRequest, session_id: int
) -> HttpResponse:
    """
    Admin view to send acceptance reminder emails.

    Sends reminder emails via background tasks to users who:
    - Have been accepted (have SessionMembership)
    - Have not yet accepted (accepted field is None)
    - Have an acceptance_deadline set
    """
    session = get_object_or_404(Session, pk=session_id)

    # Get djangonaut memberships that need reminders
    pending_memberships = (
        SessionMembership.objects.for_session(session)
        .djangonauts()
        .filter(
            accepted__isnull=True,
            acceptance_deadline__isnull=False,
        )
        .select_related("user", "team", "team__project")
    )

    if request.method == "POST":
        pending_count = pending_memberships.count()
        for membership in pending_memberships:
            tasks.send_acceptance_reminder_email.enqueue(
                membership_id=membership.pk,
            )

        messages.success(
            request,
            f"Successfully queued {pending_count} acceptance reminder(s) for '{session.title}'.",
        )
        return redirect("admin:home_session_changelist")

    context = {
        "session": session,
        "pending_count": pending_memberships.count(),
        "pending_memberships": pending_memberships,
        "opts": Session._meta,
        "site_title": "Django site admin",
        "site_header": "Django administration",
        "has_view_permission": True,
    }

    return render(request, "admin/send_acceptance_reminders.html", context)


@staff_member_required
@require_http_methods(["GET", "POST"])
def send_team_welcome_emails_view(
    request: HttpRequest, session_id: int
) -> HttpResponse:
    """
    Admin view to send team welcome emails.

    Sends group welcome emails via background tasks to teams, with each email
    going to all members (djangonauts, navigators, and captains) of that team.
    """
    session = get_object_or_404(Session, pk=session_id)

    # Get teams with members
    teams = (
        session.teams.prefetch_related("session_memberships__user")
        .filter(session_memberships__isnull=False)
        .distinct()
    )

    # Calculate counts for confirmation page
    team_count = teams.count()
    member_count = SessionMembership.objects.filter(
        session=session, team__isnull=False
    ).count()

    if request.method == "POST":
        for team in teams:
            tasks.send_team_welcome_email.enqueue(
                team_id=team.pk,
            )
        session.djangonauts_have_access = True
        session.save(update_fields=["djangonauts_have_access"])
        messages.success(
            request,
            f"Successfully queued {team_count} team welcome email(s) for '{session.title}'.",
        )
        return redirect("admin:home_session_changelist")

    context = {
        "session": session,
        "team_count": team_count,
        "member_count": member_count,
        "opts": Session._meta,
        "site_title": "Django site admin",
        "site_header": "Django administration",
        "has_view_permission": True,
    }

    return render(request, "admin/send_team_welcome_emails.html", context)
