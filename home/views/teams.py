"""Team-related views."""

from typing import Any

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.generic.detail import DetailView

from accounts.models import CustomUser
from home.models import Session, SessionMembership, Team, UserSurveyResponse


class TeamDetailView(LoginRequiredMixin, DetailView):
    """
    Display team detail page with project info, contact info, and survey responses.

    Access is restricted to team members (Captains, Navigators, and Djangonauts
    who are part of this team) and Organizers of the session.
    """

    model = Team
    template_name = "home/team_detail.html"
    context_object_name = "team"
    user_session_membership = None

    def get_queryset(self) -> QuerySet[Team]:
        """Get teams with related data prefetched."""
        return Team.objects.select_related("session", "project")

    def get_object(self, queryset: QuerySet[Team] | None = None) -> Team:
        """Get team and verify user has access."""
        team = super().get_object(queryset)

        # Check if requesting user has permissions to view the team
        self.user_session_membership = get_object_or_404(
            SessionMembership.objects.for_user(self.request.user).for_session(
                team.session
            )
        )

        # Only allow organizers or members of this specific team
        if (
            self.user_session_membership.role != SessionMembership.ORGANIZER
            and self.user_session_membership.team != team
        ):
            raise PermissionDenied("You do not have access to this team.")

        return team

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add team members and survey responses to context."""
        context = super().get_context_data(**kwargs)
        team = self.object

        # Get all team members with user details
        team_members = (
            SessionMembership.objects.accepted()
            .for_team(team)
            .select_related("user", "user__profile")
            .order_by("role", "user__first_name", "user__last_name")
        )

        # Separate by role
        context["captains"] = [
            m for m in team_members if m.role == SessionMembership.CAPTAIN
        ]
        context["navigators"] = [
            m for m in team_members if m.role == SessionMembership.NAVIGATOR
        ]
        context["djangonauts"] = [
            m for m in team_members if m.role == SessionMembership.DJANGONAUT
        ]

        # Show survey link if session is active, has survey, and user is captain/navigator
        context["show_survey_link"] = (
            team.session.is_current()
            and team.session.application_survey_id
            and self.user_session_membership.role
            in {
                SessionMembership.CAPTAIN,
                SessionMembership.NAVIGATOR,
                SessionMembership.ORGANIZER,
            }
        )

        # Add Discord invite URL from settings
        context["DISCORD_INVITE_URL"] = settings.DISCORD_INVITE_URL

        return context


class DjangonautSurveyResponseView(LoginRequiredMixin, DetailView):
    """
    Display a Djangonaut's application survey response.

    Access is restricted to Captains and Navigators on the same team as the Djangonaut,
    as well as Organizers of the session. Only available during an active session.
    """

    model = UserSurveyResponse
    template_name = "home/djangonaut_survey_response.html"
    context_object_name = "survey_response"

    def get_object(
        self, queryset: QuerySet[UserSurveyResponse] | None = None
    ) -> UserSurveyResponse:
        """Get survey response and verify access."""
        session_slug = self.kwargs.get("session_slug")
        user_id = self.kwargs.get("user_id")

        # Get the session
        self.djangonaut_membership = get_object_or_404(
            SessionMembership.objects.select_related(
                "session__application_survey", "team", "user"
            ),
            session__slug=session_slug,
            user_id=user_id,
            role=SessionMembership.DJANGONAUT,
        )

        # Check if session is current
        if not self.djangonaut_membership.session.is_current():
            raise PermissionDenied(
                "Survey responses are only visible during active sessions."
            )

        # Check if session has application survey
        if not self.djangonaut_membership.session.application_survey_id:
            raise Http404("This session does not have an application survey.")

        # Check if requesting user has permissions to view the survey responses
        self.user_session_membership = get_object_or_404(
            SessionMembership.objects.for_user(self.request.user).for_session(
                self.djangonaut_membership.session
            )
        )
        # Only allow organizers or captains/navigators on the same team
        if (
            self.user_session_membership.role != SessionMembership.ORGANIZER
            and self.user_session_membership.team != self.djangonaut_membership.team
        ):
            raise PermissionDenied("You do not have access to this team.")

        # Get the survey response
        survey_response = get_object_or_404(
            UserSurveyResponse,
            survey=self.djangonaut_membership.session.application_survey,
            user=self.djangonaut_membership.user,
        )

        return survey_response

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add survey questions and responses to context."""
        context = super().get_context_data(**kwargs)
        survey_response = self.object

        context["session"] = self.djangonaut_membership.session
        context["team"] = self.djangonaut_membership.team
        context["djangonaut"] = self.djangonaut_membership.user

        # Prefetch question responses
        question_responses = survey_response.userquestionresponse_set.select_related(
            "question"
        ).order_by("question__ordering")
        context["question_responses"] = question_responses

        return context
