"""Tests for the team-formation MCP tools in home.mcp.

Tools are called directly (the ``@server.tool`` decorator returns the
undecorated function), passing a plain ``HttpRequest`` built with
``RequestFactory`` and ``request.user`` set, the same way django-mcpz calls
them once its bearer-token ``auth`` callable has authenticated the caller.
This exercises the tool logic and its use of the admin forms without going
through the MCP JSON-RPC transport.
"""

import msgspec
from django.http import Http404
from django.test import RequestFactory, TestCase
from django_mcpz.server import ToolError

from accounts.factories import UserFactory
from home import constants
from home.factories import (
    OrganizerFactory,
    ProjectFactory,
    ProjectPreferenceFactory,
    SessionFactory,
    SessionMembershipFactory,
    SurveyFactory,
    TeamFactory,
    UserQuestionResponseFactory,
    UserSurveyResponseFactory,
)
from home.mcp import (
    AssignTeamParams,
    AutoAllocateParams,
    CheckOverlapParams,
    ListApplicantsParams,
    SessionIdParams,
    WaitlistUsersParams,
    _display_name,
    assign_users_to_team,
    auto_allocate_teams,
    check_availability_overlap,
    list_applicants,
    list_sessions,
    list_teams,
    waitlist_users,
)
from home.models import SessionMembership, Waitlist


def _as_dict(struct: msgspec.Struct) -> dict:
    return msgspec.to_builtins(struct)


class DisplayNameTests(TestCase):
    """`_display_name` must never fall back to a user's email address."""

    def test_first_and_last_name_become_first_and_initial(self):
        user = UserFactory(first_name="Ada", last_name="Lovelace")
        self.assertEqual(_display_name(user), "Ada L.")

    def test_missing_last_name_falls_back_to_first_name(self):
        user = UserFactory(first_name="Ada", last_name="")
        self.assertEqual(_display_name(user), "Ada")

    def test_missing_first_and_last_name_falls_back_to_username(self):
        user = UserFactory(first_name="", last_name="", username="ada123")
        self.assertEqual(_display_name(user), "ada123")


class TeamFormationMCPTestCase(TestCase):
    """Base fixture: an organizer, a session with an application survey, a team."""

    def setUp(self):
        self.organizer_membership = OrganizerFactory()
        self.organizer = self.organizer_membership.user
        self.session = self.organizer_membership.session
        self.survey = SurveyFactory(session=self.session)
        self.session.application_survey = self.survey
        self.session.save()

        self.project = ProjectFactory()
        self.session.available_projects.add(self.project)
        self.team = TeamFactory(session=self.session, project=self.project)

        self.request = RequestFactory().post("/mcp/team-formation/")
        self.request.user = self.organizer


class ListSessionsTests(TeamFormationMCPTestCase):
    def test_only_organized_sessions_are_listed(self):
        SessionFactory()  # a session this organizer has nothing to do with

        result = list_sessions(self.request)

        self.assertEqual([s.id for s in result.sessions], [self.session.id])


class ListApplicantsTests(TeamFormationMCPTestCase):
    def test_links_to_response_instead_of_returning_its_content(self):
        applicant = UserFactory()
        response = UserSurveyResponseFactory(user=applicant, survey=self.survey)
        UserQuestionResponseFactory(
            user_survey_response=response, value="a very secret answer"
        )

        result = list_applicants(
            self.request, ListApplicantsParams(session_id=self.session.id)
        )

        self.assertEqual(len(result.applicants), 1)
        applicant_data = result.applicants[0]
        self.assertIn(f"/{response.id}/", applicant_data.application_admin_url)
        self.assertEqual(applicant_data.name, "Jane D.")
        self.assertFalse(hasattr(applicant_data, "email"))
        serialized = repr(_as_dict(result))
        self.assertNotIn("a very secret answer", serialized)
        self.assertNotIn(applicant.email, serialized)

    def test_unknown_team_filter_raises_tool_error(self):
        with self.assertRaises(ToolError):
            list_applicants(
                self.request,
                ListApplicantsParams(session_id=self.session.id, team_id=999999),
            )

    def test_scoped_to_sessions_the_caller_organizes(self):
        other_session = SessionFactory()
        other_survey = SurveyFactory(session=other_session)
        other_session.application_survey = other_survey
        other_session.save()

        with self.assertRaises(Http404):
            list_applicants(
                self.request, ListApplicantsParams(session_id=other_session.id)
            )


class ListTeamsTests(TeamFormationMCPTestCase):
    def test_lists_team_with_members(self):
        navigator = UserFactory()
        SessionMembershipFactory(
            user=navigator,
            session=self.session,
            team=self.team,
            role=constants.NAVIGATOR,
        )

        result = list_teams(self.request, SessionIdParams(session_id=self.session.id))

        self.assertEqual(len(result.teams), 1)
        team_summary = result.teams[0]
        self.assertEqual(team_summary.id, self.team.id)
        self.assertEqual([n.user_id for n in team_summary.navigators], [navigator.id])
        self.assertEqual(result.min_navigator_meeting_hours, 5)
        self.assertEqual(result.min_captain_overlap_hours, 3)


class CheckAvailabilityOverlapTests(TeamFormationMCPTestCase):
    def test_navigator_overlap_with_no_availability_is_zero(self):
        navigator = UserFactory()
        SessionMembershipFactory(
            user=navigator,
            session=self.session,
            team=self.team,
            role=constants.NAVIGATOR,
        )
        candidate = UserFactory()

        result = check_availability_overlap(
            self.request,
            CheckOverlapParams(
                session_id=self.session.id,
                team_id=self.team.id,
                user_ids=[candidate.id],
                analysis_type="navigator",
            ),
        )

        self.assertEqual(result.hour_blocks, 0)
        self.assertFalse(result.is_sufficient)
        self.assertIsNotNone(result.compare_availability_url)

    def test_captain_overlap_without_captain_raises_tool_error(self):
        candidate = UserFactory()

        with self.assertRaises(ToolError):
            check_availability_overlap(
                self.request,
                CheckOverlapParams(
                    session_id=self.session.id,
                    team_id=self.team.id,
                    user_ids=[candidate.id],
                    analysis_type="captain",
                ),
            )


class AssignUsersToTeamTests(TeamFormationMCPTestCase):
    def test_assigns_user_and_clears_waitlist(self):
        applicant = UserFactory()
        UserSurveyResponseFactory(user=applicant, survey=self.survey)
        Waitlist.objects.create(user=applicant, session=self.session)

        result = assign_users_to_team(
            self.request,
            AssignTeamParams(
                session_id=self.session.id,
                team_id=self.team.id,
                user_ids=[applicant.id],
            ),
        )

        self.assertEqual(result.assigned_count, 1)
        membership = SessionMembership.objects.get(user=applicant, session=self.session)
        self.assertEqual(membership.team, self.team)
        self.assertFalse(
            Waitlist.objects.filter(user=applicant, session=self.session).exists()
        )

    def test_mismatched_project_preference_raises_tool_error(self):
        applicant = UserFactory()
        UserSurveyResponseFactory(user=applicant, survey=self.survey)
        other_project = ProjectFactory()
        self.session.available_projects.add(other_project)
        ProjectPreferenceFactory(
            user=applicant, session=self.session, project=other_project
        )

        with self.assertRaises(ToolError) as cm:
            assign_users_to_team(
                self.request,
                AssignTeamParams(
                    session_id=self.session.id,
                    team_id=self.team.id,
                    user_ids=[applicant.id],
                ),
            )
        self.assertNotIn(applicant.email, str(cm.exception))
        self.assertIn("Jane D.", str(cm.exception))


class WaitlistUsersTests(TeamFormationMCPTestCase):
    def test_removes_existing_membership_and_waitlists(self):
        applicant = UserFactory()
        UserSurveyResponseFactory(user=applicant, survey=self.survey)
        SessionMembershipFactory(
            user=applicant,
            session=self.session,
            team=self.team,
            role=constants.DJANGONAUT,
        )

        result = waitlist_users(
            self.request,
            WaitlistUsersParams(session_id=self.session.id, user_ids=[applicant.id]),
        )

        self.assertEqual(result.waitlisted_count, 1)
        self.assertEqual(result.removed_from_team_count, 1)
        self.assertFalse(
            SessionMembership.objects.filter(
                user=applicant, session=self.session
            ).exists()
        )
        self.assertTrue(
            Waitlist.objects.filter(user=applicant, session=self.session).exists()
        )


class AutoAllocateTeamsTests(TeamFormationMCPTestCase):
    def test_preview_does_not_persist_without_apply(self):
        # The organizer's own membership is the only one that should exist
        # before or after a preview (apply=False) run.
        baseline_count = SessionMembership.objects.count()

        result = auto_allocate_teams(
            self.request, AutoAllocateParams(session_id=self.session.id, apply=False)
        )

        self.assertFalse(result.applied)
        self.assertEqual(result.total_teams, 1)
        self.assertEqual(SessionMembership.objects.count(), baseline_count)

    def test_apply_persists_allocation(self):
        result = auto_allocate_teams(
            self.request, AutoAllocateParams(session_id=self.session.id, apply=True)
        )

        self.assertTrue(result.applied)
        self.assertEqual(result.allocated_count, 0)
