"""
Admin views for the Discord session setup and teardown actions.

Setup and teardown render a confirmation page on GET so organizers can
review the scope (and chase missing Discord usernames) before anything hits
the Discord API, then enqueue a background task on POST — the orchestration
makes far too many API calls to run inside a request. The task emails the
report to the requesting user; for setup it links to the team-messages view
below, which regenerates the copy/paste welcome messages from the database
on demand.
"""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from home import tasks
from home.integrations.discord.service import discord_enabled
from home.integrations.discord.session_service import build_team_messages
from home.models import Session


def _members_without_discord_username(session: Session) -> list:
    """Users the actions can't map to Discord, for pre-run warnings."""
    return [
        membership.user
        for membership in session.session_memberships.accepted()
        .without_discord_username()
        .select_related("user__profile")
    ]


def _other_active_discord_session(session: Session) -> Session | None:
    """Another session whose Discord is still set up, if any.

    Setup and teardown both touch guild-wide program roles, so only one
    session may have Discord active at a time; teardown of one session while
    another is active would strip the other's roles. Returns the blocking
    session so the views can refuse and name it.
    """
    return Session.objects.with_active_discord().exclude(pk=session.pk).first()


def _admin_context(request: HttpRequest, session: Session, **extra) -> dict:
    context = {
        "session": session,
        "opts": Session._meta,
        "site_title": "Django site admin",
        "site_header": "Django administration",
        "has_view_permission": True,
    }
    context.update(extra)
    return context


@staff_member_required
@require_http_methods(["GET", "POST"])
def discord_setup_view(request: HttpRequest, session_id: int) -> HttpResponse:
    """Create/update the session's Discord category, channels, and roles."""
    session = get_object_or_404(
        Session.objects.for_admin_site(request.user), id=session_id
    )
    if not discord_enabled():
        messages.error(
            request,
            "Discord integration is not configured "
            "(DISCORD_BOT_TOKEN / DISCORD_GUILD_ID).",
        )
        return redirect("admin:home_session_changelist")

    blocking_session = _other_active_discord_session(session)
    if blocking_session is not None:
        messages.error(
            request,
            f"'{blocking_session.title}' still has Discord set up. Tear it down "
            "before setting up Discord for another session.",
        )
        return redirect("admin:home_session_changelist")

    if request.method == "POST":
        tasks.setup_session_discord.enqueue(
            session_id=session.pk, user_id=request.user.pk
        )
        messages.success(
            request,
            f"Discord setup for '{session.title}' is running in the background. "
            f"A report will be emailed to {request.user.email} when it completes.",
        )
        return redirect("admin:home_session_changelist")

    context = _admin_context(
        request,
        session,
        team_count=session.teams.count(),
        member_count=session.session_memberships.accepted().count(),
        members_without_username=_members_without_discord_username(session),
    )
    return render(request, "admin/discord_setup.html", context)


@staff_member_required
@require_http_methods(["GET", "POST"])
def discord_teardown_view(request: HttpRequest, session_id: int) -> HttpResponse:
    """Archive the session's Discord channels and hand out alumni roles."""
    session = get_object_or_404(
        Session.objects.for_admin_site(request.user), id=session_id
    )
    if not discord_enabled():
        messages.error(
            request,
            "Discord integration is not configured "
            "(DISCORD_BOT_TOKEN / DISCORD_GUILD_ID).",
        )
        return redirect("admin:home_session_changelist")

    # Only relevant when this session is actually set up; otherwise teardown
    # errors out on its own before touching any guild-wide roles.
    if session.discord_category_id:
        blocking_session = _other_active_discord_session(session)
        if blocking_session is not None:
            messages.error(
                request,
                f"'{blocking_session.title}' also has Discord set up. Teardown "
                "strips program roles across the whole server, so tear down one "
                "session at a time.",
            )
            return redirect("admin:home_session_changelist")

    if request.method == "POST":
        if not session.discord_category_id:
            messages.error(
                request,
                "This session has no Discord category recorded. Run the "
                "Discord setup action first.",
            )
            return redirect("admin:home_session_changelist")
        tasks.teardown_session_discord.enqueue(
            session_id=session.pk, user_id=request.user.pk
        )
        messages.success(
            request,
            f"Discord teardown for '{session.title}' is running in the "
            f"background. A report will be emailed to {request.user.email} "
            "when it completes.",
        )
        return redirect("admin:home_session_changelist")

    context = _admin_context(
        request,
        session,
        team_count=session.teams.count(),
        member_count=session.session_memberships.accepted().count(),
        members_without_username=_members_without_discord_username(session),
        has_category=bool(session.discord_category_id),
    )
    return render(request, "admin/discord_teardown.html", context)


@staff_member_required
@require_http_methods(["GET"])
def discord_team_messages_view(request: HttpRequest, session_id: int) -> HttpResponse:
    """Show the copy/paste welcome message for each team channel.

    Generated from the database on request, so organizers can come back for
    the messages whenever they need them — not only right after setup.
    """
    session = get_object_or_404(
        Session.objects.for_admin_site(request.user), id=session_id
    )
    context = _admin_context(
        request, session, team_messages=build_team_messages(session)
    )
    return render(request, "admin/discord_team_messages.html", context)
