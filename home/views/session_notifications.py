"""
Views for sending session-related notifications.

Provides admin interfaces for:
- Sending session result notifications (accepted/waitlist/rejected)
- Sending acceptance reminder emails
- Sending team welcome emails
"""

import datetime
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from home import email
from home.forms import SendSessionResultsForm
from home.models import Session, SessionMembership, Team, UserSurveyResponse, Waitlist


# Email sending functions (to be moved to background tasks in the future)


def send_accepted_emails(
    session: Session, accepted_memberships: QuerySet[SessionMembership]
) -> int:
    """
    Send acceptance emails to users with SessionMembership.

    Args:
        session: The session for which to send emails
        accepted_memberships: QuerySet of SessionMembership objects

    Returns:
        Number of emails sent
    """
    sent_count = 0

    for membership in accepted_memberships:
        acceptance_url = settings.BASE_URL + reverse(
            "accept_membership", kwargs={"slug": membership.session.slug}
        )

        context = {
            "user": membership.user,
            "name": membership.user.first_name or membership.user.email,
            "session": session,
            "membership": membership,
            "acceptance_url": acceptance_url,
            "cta_link": acceptance_url,
        }

        email.send(
            email_template="session_accepted",
            recipient_list=[membership.user.email],
            context=context,
        )
        sent_count += 1

    return sent_count


def send_waitlisted_emails(
    session: Session,
    waitlisted_entries: QuerySet[Waitlist],
    applicant_count: int,
    accepted_count: int,
) -> int:
    """
    Send waitlist emails to users on the Waitlist.

    Args:
        session: The session for which to send emails
        waitlisted_entries: QuerySet of Waitlist objects
        applicant_count: Total number of applicants
        accepted_count: Number of accepted applicants

    Returns:
        Number of emails sent
    """
    sent_count = 0

    for waitlist_entry in waitlisted_entries:
        context = {
            "user": waitlist_entry.user,
            "session": session,
            "applicant_count": applicant_count,
            "accepted_count": accepted_count,
        }

        email.send(
            email_template="session_waitlisted",
            recipient_list=[waitlist_entry.user.email],
            context=context,
        )
        sent_count += 1

    return sent_count


def send_rejected_emails(
    session: Session,
    rejected_user_ids: set[int],
    applicant_responses: QuerySet[UserSurveyResponse],
    applicant_count: int,
    accepted_count: int,
) -> int:
    """
    Send rejection emails to users who applied but were neither accepted nor waitlisted.

    Args:
        session: The session for which to send emails
        rejected_user_ids: Set of user IDs who were rejected
        applicant_responses: QuerySet of UserSurveyResponse objects
        applicant_count: Total number of applicants
        accepted_count: Number of accepted applicants

    Returns:
        Number of emails sent
    """
    sent_count = 0

    for user_id in rejected_user_ids:
        response = applicant_responses.get(user_id=user_id)
        context = {
            "user": response.user,
            "session": session,
            "applicant_count": applicant_count,
            "accepted_count": accepted_count,
        }

        email.send(
            email_template="session_rejected",
            recipient_list=[response.user.email],
            context=context,
        )
        sent_count += 1

    return sent_count


def send_acceptance_reminder_emails(
    session: Session, pending_memberships: QuerySet[SessionMembership]
) -> int:
    """
    Send acceptance reminder emails to users who haven't yet accepted.

    Args:
        session: The session for which to send emails
        pending_memberships: QuerySet of SessionMembership objects with pending acceptance

    Returns:
        Number of emails sent
    """
    sent_count = 0

    for membership in pending_memberships:
        acceptance_url = settings.BASE_URL + reverse(
            "accept_membership", kwargs={"slug": membership.session.slug}
        )

        context = {
            "user": membership.user,
            "name": membership.user.first_name or membership.user.email,
            "session": session,
            "membership": membership,
            "acceptance_url": acceptance_url,
            "cta_link": acceptance_url,
        }

        email.send(
            email_template="acceptance_reminder",
            recipient_list=[membership.user.email],
            context=context,
        )
        sent_count += 1

    return sent_count


def send_team_welcome_emails(session: Session, teams: QuerySet[Team]) -> int:
    """
    Send group welcome emails to teams.

    Each team receives a single email sent to all members (djangonauts, navigators, captains).

    Args:
        session: The session for which to send emails
        teams: QuerySet of Team objects

    Returns:
        Number of emails sent
    """
    sent_count = 0

    for team in teams:
        # Get all team members for this team
        team_members = (
            SessionMembership.objects.filter(team=team)
            .select_related("user")
            .order_by("role", "user__first_name")
        )

        if not team_members.exists():
            continue

        # Separate members by role
        djangonauts = [
            m for m in team_members if m.role == SessionMembership.DJANGONAUT
        ]
        navigators = [m for m in team_members if m.role == SessionMembership.NAVIGATOR]
        captains = [m for m in team_members if m.role == SessionMembership.CAPTAIN]

        # Collect all team member emails
        recipient_list = [member.user.email for member in team_members]

        context = {
            "session": session,
            "team": team,
            "team_members": team_members,
            "djangonauts": djangonauts,
            "navigators": navigators,
            "captains": captains,
            "discord_invite_url": settings.DISCORD_INVITE_URL,
        }

        email.send(
            email_template="team_welcome",
            recipient_list=recipient_list,
            context=context,
        )
        sent_count += 1

    return sent_count


def send_membership_acceptance_emails(
    memberships: QuerySet[SessionMembership],
) -> int:
    """
    Send acceptance emails to users with SessionMembership.

    Args:
        memberships: QuerySet of SessionMembership objects

    Returns:
        Number of emails sent
    """
    sent_count = 0

    for membership in memberships:
        acceptance_url = settings.BASE_URL + reverse(
            "accept_membership", kwargs={"slug": membership.session.slug}
        )

        context = {
            "user": membership.user,
            "name": membership.user.first_name or membership.user.email,
            "session": membership.session,
            "membership": membership,
            "acceptance_url": acceptance_url,
            "cta_link": acceptance_url,
        }

        email.send(
            email_template="session_accepted",
            recipient_list=[membership.user.email],
            context=context,
        )
        sent_count += 1

    return sent_count


def reject_waitlisted_user(waitlist_entry: Waitlist) -> None:
    """
    Reject a waitlisted user and send them a rejection email.

    Sends a waitlist rejection notification email and removes the user
    from the waitlist.

    Args:
        waitlist_entry: The Waitlist entry to reject
    """
    context = {
        "user": waitlist_entry.user,
        "session": waitlist_entry.session,
    }

    email.send(
        email_template="waitlist_rejection",
        recipient_list=[waitlist_entry.user.email],
        context=context,
    )

    # Remove from waitlist
    waitlist_entry.delete()


@staff_member_required
@require_http_methods(["GET", "POST"])
def send_session_results_view(request: HttpRequest, session_id: int) -> HttpResponse:
    """
    Admin view to send session result notifications.

    Sends three types of emails:
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

            # Send accepted emails (only to Djangonauts)
            sent_accepted_count = send_accepted_emails(session, djangonaut_memberships)

            # Send waitlisted emails
            sent_waitlisted_count = send_waitlisted_emails(
                session, waitlisted_entries, applicant_count, accepted_count
            )

            # Send rejected emails
            sent_rejected_count = send_rejected_emails(
                session,
                rejected_user_ids,
                applicant_responses,
                applicant_count,
                accepted_count,
            )

            # Mark notifications as sent
            session.results_notifications_sent_at = timezone.now()
            session.save(update_fields=["results_notifications_sent_at"])

            messages.success(
                request,
                f"Successfully sent {sent_accepted_count} accepted, "
                f"{sent_waitlisted_count} waitlisted, and "
                f"{sent_rejected_count} rejected notifications for '{session.title}'.",
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

    Sends reminder emails to users who:
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
        sent_count = send_acceptance_reminder_emails(session, pending_memberships)

        messages.success(
            request,
            f"Successfully sent {sent_count} acceptance reminder(s) for '{session.title}'.",
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

    Sends group welcome emails to teams, with each email going to
    all members (djangonauts, navigators, and captains) of that team.
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
        sent_count = send_team_welcome_emails(session, teams)

        messages.success(
            request,
            f"Successfully sent {sent_count} team welcome email(s) for '{session.title}'.",
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
