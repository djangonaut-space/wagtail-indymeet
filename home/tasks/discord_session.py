"""
Background tasks for the Discord session setup and teardown actions.

The orchestrations make dozens of Discord API calls, far too slow to run
inside a request. The admin views enqueue these tasks and each task emails
the requesting user the report when it finishes — including a link to the
admin page that generates the per-team welcome messages after setup.
"""

import logging

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django_tasks import task

from home import email
from home.integrations.discord.session_service import (
    DiscordSessionSetup,
    DiscordSessionTeardown,
    SetupReport,
    TeardownReport,
)
from home.models import Session
from home.services.session_announcements import generate_announcements

logger = logging.getLogger(__name__)


def _superuser_cc_list(report, requesting_user) -> list[str] | None:
    """Superusers to CC on the report email when the run had errors.

    Errors usually mean the Discord server needs an admin's attention
    (missing roles, permission problems), and the requesting organizer may
    not be able to fix them alone.
    """
    if not report.errors:
        return None
    return list(
        get_user_model()
        .objects.filter(is_superuser=True)
        .exclude(pk=requesting_user.pk)
        .exclude(email="")
        .values_list("email", flat=True)
    )


@task()
def setup_session_discord(session_id: int, user_id: int) -> None:
    """Run Discord setup for a session and email the requester the report."""
    session = Session.objects.get(pk=session_id)
    user = get_user_model().objects.get(pk=user_id)
    try:
        report = DiscordSessionSetup(session).run()
    except requests.RequestException:
        logger.exception("Discord setup failed for session %s", session_id)
        report = SetupReport(
            errors=[
                "A Discord API error interrupted the setup; check the logs "
                "for details. Setup is idempotent, so it is safe to run again."
            ]
        )
    if not report.errors:
        # Only once the announcements channel exists, since that is where
        # these get posted. Generation is additive, so a rerun leaves any
        # announcements organizers have already edited or approved alone.
        report.announcements_created = generate_announcements(session)
    team_messages_url = settings.BASE_URL + reverse(
        "admin:session_discord_team_messages", args=[session.pk]
    )
    email.send(
        from_email=settings.SESSIONS_FROM_EMAIL,
        email_template="discord_setup_complete",
        recipient_list=[user.email],
        cc_list=_superuser_cc_list(report, user),
        context={
            "user": user,
            "name": user.first_name or user.email,
            "session": session,
            "report": report,
            "team_messages_url": team_messages_url,
            "cta_link": team_messages_url,
        },
    )


@task()
def teardown_session_discord(session_id: int, user_id: int) -> None:
    """Run Discord teardown for a session and email the requester the report."""
    session = Session.objects.get(pk=session_id)
    user = get_user_model().objects.get(pk=user_id)
    try:
        report = DiscordSessionTeardown(session).run()
    except ValueError as exc:
        report = TeardownReport(errors=[str(exc)])
    except requests.RequestException:
        logger.exception("Discord teardown failed for session %s", session_id)
        report = TeardownReport(
            errors=[
                "A Discord API error interrupted the teardown; check the "
                "logs for details."
            ]
        )
    changelist_url = settings.BASE_URL + reverse("admin:home_session_changelist")
    email.send(
        from_email=settings.SESSIONS_FROM_EMAIL,
        email_template="discord_teardown_complete",
        recipient_list=[user.email],
        cc_list=_superuser_cc_list(report, user),
        context={
            "user": user,
            "name": user.first_name or user.email,
            "session": session,
            "report": report,
            "cta_link": changelist_url,
        },
    )
