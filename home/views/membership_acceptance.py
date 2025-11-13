"""
View for users to accept or decline their session membership.

Allows accepted users to confirm their participation in a session.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from home.forms import MembershipAcceptanceForm
from home.models import Session, SessionMembership


@login_required
@require_http_methods(["GET", "POST"])
def accept_membership_view(request: HttpRequest, slug: str) -> HttpResponse:
    """
    View for users to accept or decline their session membership.

    GET: Display the acceptance form with session and team details
    POST: Process the user's acceptance or decline decision

    Args:
        request: The HTTP request
        slug: The slug of the session (membership looked up by user + session)

    Returns:
        HTTP response with the acceptance form or redirect
    """
    # Look up Djangonaut membership based on session slug and current user
    session = get_object_or_404(Session, slug=slug)
    membership = get_object_or_404(
        SessionMembership.objects.for_session(session)
        .djangonauts()
        .select_related(
            "session",
            "team",
            "team__project",
            "user",
        ),
        user=request.user,
    )

    # Check if already responded
    if membership.accepted is not None:
        context = {
            "membership": membership,
            "already_responded": True,
            "accepted": membership.accepted,
            "accepted_at": membership.accepted_at,
        }
        return render(request, "home/session/membership_acceptance.html", context)

    if request.method == "POST":
        form = MembershipAcceptanceForm(request.POST, membership=membership)
        if form.is_valid():
            is_accepted = form.save()

            if is_accepted:
                messages.success(
                    request,
                    f"Congratulations! You've confirmed your participation in "
                    f"{membership.session.title}. We'll send you more details "
                    f"soon!",
                )
                return redirect("session_detail", slug=membership.session.slug)
            else:
                messages.info(
                    request,
                    f"You've declined participation in {membership.session.title}. "
                    "We're sorry you won't be joining us this time.",
                )
                return redirect("session_list")
    else:
        form = MembershipAcceptanceForm(membership=membership)

    context = {
        "membership": membership,
        "already_responded": False,
        "form": form,
    }

    return render(request, "home/session/membership_acceptance.html", context)
