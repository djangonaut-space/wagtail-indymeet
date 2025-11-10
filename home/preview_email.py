"""
Email preview utilities for testing email templates.

Provides functions to send preview emails to admin users for visual testing.
"""

from django.conf import settings
from django.contrib import admin, messages
from django.urls import reverse

from . import email
from .models import Session, SessionMembership, Team, UserSurveyResponse, Waitlist


def acceptance_email(recipient_email: str, membership: SessionMembership) -> None:
    """
    Send a preview of the acceptance email.

    Args:
        recipient_email: Email address to send preview to
        membership: SessionMembership to use for preview data
    """
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
        recipient_list=[recipient_email],
        context=context,
    )


def reminder_email(recipient_email: str, membership: SessionMembership) -> None:
    """
    Send a preview of the acceptance reminder email.

    Args:
        recipient_email: Email address to send preview to
        membership: SessionMembership to use for preview data
    """
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
        recipient_list=[recipient_email],
        context=context,
    )


def rejection_email(recipient_email: str, session: Session) -> None:
    """
    Send a preview of the rejection email.

    Args:
        recipient_email: Email address to send preview to
        session: Session to use for preview data

    Raises:
        ValueError: If session has no application survey or no applicants found
    """
    if not session.application_survey:
        raise ValueError("Session has no application survey")

    sample_response = UserSurveyResponse.objects.filter(
        survey=session.application_survey
    ).first()

    if not sample_response:
        raise ValueError("No applicants found for this session")

    applicant_count = UserSurveyResponse.objects.filter(
        survey=session.application_survey
    ).count()
    accepted_count = SessionMembership.objects.filter(
        session=session, role=SessionMembership.DJANGONAUT
    ).count()

    context = {
        "user": sample_response.user,
        "session": session,
        "applicant_count": applicant_count,
        "accepted_count": accepted_count,
    }

    email.send(
        email_template="session_rejected",
        recipient_list=[recipient_email],
        context=context,
    )


def waitlist_email(recipient_email: str, session: Session) -> None:
    """
    Send a preview of the waitlist email.

    Args:
        recipient_email: Email address to send preview to
        session: Session to use for preview data

    Raises:
        ValueError: If no waitlisted users found for session
    """
    sample_waitlist = Waitlist.objects.filter(session=session).first()

    if not sample_waitlist:
        raise ValueError("No waitlisted users found for this session")

    applicant_count = (
        UserSurveyResponse.objects.filter(survey=session.application_survey).count()
        if session.application_survey
        else 0
    )
    accepted_count = SessionMembership.objects.filter(
        session=session, role=SessionMembership.DJANGONAUT
    ).count()

    context = {
        "user": sample_waitlist.user,
        "session": session,
        "applicant_count": applicant_count,
        "accepted_count": accepted_count,
    }

    email.send(
        email_template="session_waitlisted",
        recipient_list=[recipient_email],
        context=context,
    )


def team_welcome_email(recipient_email: str, session: Session) -> None:
    """
    Send a preview of the team welcome email.

    Args:
        recipient_email: Email address to send preview to
        session: Session to use for preview data

    Raises:
        ValueError: If no teams with members found for session
    """
    team = (
        Team.objects.filter(session=session, session_memberships__isnull=False)
        .distinct()
        .first()
    )

    if not team:
        raise ValueError("No teams with members found for this session")

    team_members = (
        SessionMembership.objects.filter(team=team)
        .select_related("user")
        .order_by("role", "user__first_name")
    )

    djangonauts = [m for m in team_members if m.role == SessionMembership.DJANGONAUT]
    navigators = [m for m in team_members if m.role == SessionMembership.NAVIGATOR]
    captains = [m for m in team_members if m.role == SessionMembership.CAPTAIN]

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
        recipient_list=[recipient_email],
        context=context,
    )


# Admin actions for SessionMembershipAdmin


@admin.action(description="Preview acceptance email (send to me)")
def acceptance_email_action(modeladmin, request, queryset):
    """Send a preview of the acceptance email to the logged-in admin user."""
    membership = queryset.filter(role=SessionMembership.DJANGONAUT).first()
    if not membership:
        modeladmin.message_user(
            request,
            "No Djangonaut membership found in selection",
            messages.ERROR,
        )
        return

    acceptance_email(request.user.email, membership)

    modeladmin.message_user(
        request,
        f"Preview of acceptance email sent to {request.user.email}",
        messages.SUCCESS,
    )


@admin.action(description="Preview reminder email (send to me)")
def reminder_email_action(modeladmin, request, queryset):
    """Send a preview of the acceptance reminder email to the logged-in admin user."""
    membership = queryset.filter(role=SessionMembership.DJANGONAUT).first()
    if not membership:
        modeladmin.message_user(
            request,
            "No Djangonaut membership found in selection",
            messages.ERROR,
        )
        return

    reminder_email(request.user.email, membership)

    modeladmin.message_user(
        request,
        f"Preview of reminder email sent to {request.user.email}",
        messages.SUCCESS,
    )


# Admin actions for SessionAdmin


@admin.action(description="Preview rejection email (send to me)")
def rejection_email_action(modeladmin, request, queryset):
    """Send a preview of the rejection email to the logged-in admin user."""
    if queryset.count() != 1:
        modeladmin.message_user(
            request,
            "Please select exactly one session.",
            messages.ERROR,
        )
        return

    session = queryset.first()

    try:
        rejection_email(request.user.email, session)
        modeladmin.message_user(
            request,
            f"Preview of rejection email sent to {request.user.email}",
            messages.SUCCESS,
        )
    except ValueError as e:
        modeladmin.message_user(request, str(e), messages.ERROR)


@admin.action(description="Preview waitlist email (send to me)")
def waitlist_email_action(modeladmin, request, queryset):
    """Send a preview of the waitlist email to the logged-in admin user."""
    if queryset.count() != 1:
        modeladmin.message_user(
            request,
            "Please select exactly one session.",
            messages.ERROR,
        )
        return

    session = queryset.first()

    try:
        waitlist_email(request.user.email, session)
        modeladmin.message_user(
            request,
            f"Preview of waitlist email sent to {request.user.email}",
            messages.SUCCESS,
        )
    except ValueError as e:
        modeladmin.message_user(request, str(e), messages.ERROR)


@admin.action(description="Preview team welcome email (send to me)")
def team_welcome_email_action(modeladmin, request, queryset):
    """Send a preview of the team welcome email to the logged-in admin user."""
    if queryset.count() != 1:
        modeladmin.message_user(
            request,
            "Please select exactly one session.",
            messages.ERROR,
        )
        return

    session = queryset.first()

    try:
        team_welcome_email(request.user.email, session)
        modeladmin.message_user(
            request,
            f"Preview of team welcome email sent to {request.user.email}",
            messages.SUCCESS,
        )
    except ValueError as e:
        modeladmin.message_user(request, str(e), messages.ERROR)
