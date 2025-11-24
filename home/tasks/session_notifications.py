"""
Background tasks for sending session-related notification emails.

These tasks handle sending various notification emails asynchronously,
allowing views to return immediately while emails are processed in the background.
"""

from django.conf import settings
from django.urls import reverse
from django_tasks import task

from home import email
from home.models import Session, SessionMembership, Team, UserSurveyResponse, Waitlist


@task()
def send_accepted_email(membership_id: int) -> None:
    """
    Send an acceptance email to a user with SessionMembership.

    Args:
        membership_id: The ID of the SessionMembership
    """
    membership = SessionMembership.objects.select_related(
        "user", "session", "team", "team__project"
    ).get(pk=membership_id)

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


@task()
def send_waitlisted_email(
    waitlist_id: int,
    applicant_count: int,
    accepted_count: int,
) -> None:
    """
    Send a waitlist email to a user on the Waitlist.

    Args:
        waitlist_id: The ID of the Waitlist entry
        applicant_count: Total number of applicants
        accepted_count: Number of accepted applicants
    """
    waitlist_entry = Waitlist.objects.select_related("user", "session").get(
        pk=waitlist_id
    )

    context = {
        "user": waitlist_entry.user,
        "session": waitlist_entry.session,
        "applicant_count": applicant_count,
        "accepted_count": accepted_count,
    }

    email.send(
        email_template="session_waitlisted",
        recipient_list=[waitlist_entry.user.email],
        context=context,
    )


@task()
def send_rejected_email(
    user_id: int,
    session_id: int,
    applicant_count: int,
    accepted_count: int,
) -> None:
    """
    Send a rejection email to a user who applied but was not accepted or waitlisted.

    Args:
        user_id: The ID of the rejected user
        session_id: The ID of the Session
        applicant_count: Total number of applicants
        accepted_count: Number of accepted applicants
    """
    session = Session.objects.get(pk=session_id)
    response = UserSurveyResponse.objects.select_related("user").get(
        survey=session.application_survey, user_id=user_id
    )

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


@task()
def send_acceptance_reminder_email(membership_id: int) -> None:
    """
    Send an acceptance reminder email to a user who hasn't yet accepted.

    Args:
        membership_id: The ID of the SessionMembership
    """
    membership = SessionMembership.objects.select_related(
        "user", "session", "team", "team__project"
    ).get(pk=membership_id)

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
        email_template="acceptance_reminder",
        recipient_list=[membership.user.email],
        context=context,
    )


@task()
def send_team_welcome_email(team_id: int) -> None:
    """
    Send a group welcome email to a team.

    The email is sent to all team members (djangonauts, navigators, captains).

    Args:
        team_id: The ID of the Team
    """
    team = Team.objects.select_related("project", "session").get(pk=team_id)

    # Get all team members for this team
    team_members = (
        SessionMembership.objects.filter(team=team)
        .select_related("user")
        .order_by("role", "user__first_name")
    )

    if not team_members.exists():
        return

    # Separate members by role
    djangonauts = [m for m in team_members if m.role == SessionMembership.DJANGONAUT]
    navigators = [m for m in team_members if m.role == SessionMembership.NAVIGATOR]
    captains = [m for m in team_members if m.role == SessionMembership.CAPTAIN]

    # Collect all team member emails
    recipient_list = [member.user.email for member in team_members]

    context = {
        "session": team.session,
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


@task()
def send_membership_acceptance_email(membership_id: int) -> None:
    """
    Send an acceptance email to a user with SessionMembership.

    This task is used for ad-hoc acceptance emails (e.g., when promoting from waitlist)
    rather than the bulk send_session_results flow.

    Args:
        membership_id: The ID of the SessionMembership
    """
    membership = SessionMembership.objects.select_related(
        "user", "session", "team", "team__project"
    ).get(pk=membership_id)

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


@task()
def reject_waitlisted_user(waitlist_id: int) -> None:
    """
    Reject a waitlisted user and send them a rejection email.

    Sends a waitlist rejection notification email and marks the user as notified
    by setting the notified_at timestamp. If the user has already been notified
    (notified_at is set), this task does nothing to prevent duplicate notifications.

    Args:
        waitlist_id: The ID of the Waitlist entry to reject
    """
    from django.utils import timezone

    waitlist_entry = Waitlist.objects.select_related("user", "session").get(
        pk=waitlist_id
    )

    # Skip if user has already been notified
    if waitlist_entry.notified_at is not None:
        return

    context = {
        "user": waitlist_entry.user,
        "session": waitlist_entry.session,
    }

    email.send(
        email_template="waitlist_rejection",
        recipient_list=[waitlist_entry.user.email],
        context=context,
    )

    # Mark as notified instead of deleting
    waitlist_entry.notified_at = timezone.now()
    waitlist_entry.save(update_fields=["notified_at"])
