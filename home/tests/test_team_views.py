"""Tests for team-related views."""

from datetime import datetime, timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from accounts.factories import UserFactory
from home.factories import (
    ProjectFactory,
    QuestionFactory,
    SessionFactory,
    SessionMembershipFactory,
    SurveyFactory,
    UserQuestionResponseFactory,
    UserSurveyResponseFactory,
)
from home.models import SessionMembership, Team


@freeze_time("2024-06-15")
class TeamDetailViewTests(TestCase):
    """Tests for TeamDetailView."""

    def setUp(self) -> None:
        """Set up test data."""
        super().setUp()
        self.client = Client()

        # Create a current session (active now)
        self.current_session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 8, 30).date(),
            application_start_date=datetime(2024, 5, 1).date(),
            application_end_date=datetime(2024, 5, 31).date(),
        )

        # Create application survey
        self.survey = SurveyFactory.create(name="Application Survey")
        self.current_session.application_survey = self.survey
        self.current_session.save()

        # Create questions
        self.question1 = QuestionFactory.create(
            survey=self.survey, label="Why do you want to join?"
        )
        self.question2 = QuestionFactory.create(
            survey=self.survey, label="What is your experience level?"
        )

        # Create project and team
        self.project = ProjectFactory.create(name="Django")
        self.team = Team.objects.create(
            session=self.current_session,
            project=self.project,
            name="Team Alpha",
            google_drive_folder="https://drive.google.com/folder/123",
        )

        # Create users
        self.captain = UserFactory.create(
            first_name="Captain", last_name="Marvel", email="captain@test.com"
        )
        self.navigator = UserFactory.create(
            first_name="Navigator", last_name="Smith", email="navigator@test.com"
        )
        self.djangonaut1 = UserFactory.create(
            first_name="Django", last_name="Learner", email="djangonaut1@test.com"
        )
        self.djangonaut2 = UserFactory.create(
            first_name="Python", last_name="Student", email="djangonaut2@test.com"
        )
        self.other_user = UserFactory.create(
            first_name="Other", last_name="User", email="other@test.com"
        )

        # Create memberships
        self.captain_membership = SessionMembershipFactory.create(
            user=self.captain,
            session=self.current_session,
            team=self.team,
            role=SessionMembership.CAPTAIN,
            accepted=True,
        )
        self.navigator_membership = SessionMembershipFactory.create(
            user=self.navigator,
            session=self.current_session,
            team=self.team,
            role=SessionMembership.NAVIGATOR,
            accepted=True,
        )
        self.djangonaut1_membership = SessionMembershipFactory.create(
            user=self.djangonaut1,
            session=self.current_session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )
        self.djangonaut2_membership = SessionMembershipFactory.create(
            user=self.djangonaut2,
            session=self.current_session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )

        # Create survey responses for Djangonauts
        self.response1 = UserSurveyResponseFactory.create(
            user=self.djangonaut1, survey=self.survey
        )
        UserQuestionResponseFactory.create(
            user_survey_response=self.response1,
            question=self.question1,
            value="I want to contribute to Django",
        )
        UserQuestionResponseFactory.create(
            user_survey_response=self.response1,
            question=self.question2,
            value="Intermediate",
        )

        self.response2 = UserSurveyResponseFactory.create(
            user=self.djangonaut2, survey=self.survey
        )
        UserQuestionResponseFactory.create(
            user_survey_response=self.response2,
            question=self.question1,
            value="I love Python and Django",
        )
        UserQuestionResponseFactory.create(
            user_survey_response=self.response2,
            question=self.question2,
            value="Beginner",
        )

        self.url = reverse(
            "team_detail",
            kwargs={"session_slug": self.current_session.slug, "pk": self.team.pk},
        )

    def test_anonymous_user_redirected_to_login(self) -> None:
        """Test that anonymous users are redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_non_session_member_gets_404(self) -> None:
        """Test that users not in the session get a 404 Not Found."""
        self.client.force_login(self.other_user)
        response = self.client.get(self.url)
        # get_object_or_404 returns 404 when user has no membership in session
        self.assertEqual(response.status_code, 404)

    def test_captain_can_view_team_page(self) -> None:
        """Test that captain can view team page."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/session/team/team_detail.html")

    def test_navigator_can_view_team_page(self) -> None:
        """Test that navigator can view team page."""
        self.client.force_login(self.navigator)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/session/team/team_detail.html")

    def test_djangonaut_can_view_team_page(self) -> None:
        """Test that djangonaut can view team page."""
        self.client.force_login(self.djangonaut1)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/session/team/team_detail.html")

    def test_organizer_can_view_any_team_page(self) -> None:
        """Test that organizer can view any team page in their session."""
        # Create organizer without team assignment
        organizer = UserFactory.create(
            first_name="Organizer", last_name="Admin", email="organizer@test.com"
        )
        SessionMembershipFactory.create(
            user=organizer,
            session=self.current_session,
            team=None,  # No team assigned
            role=SessionMembership.ORGANIZER,
            accepted=True,
        )

        self.client.force_login(organizer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/session/team/team_detail.html")

    def test_organizer_from_different_session_gets_404(self) -> None:
        """Test that organizer from different session cannot view team."""
        # Create a different session
        other_session = SessionFactory.create(
            start_date=datetime(2024, 9, 1).date(),
            end_date=datetime(2024, 11, 30).date(),
        )

        # Create organizer for different session
        organizer = UserFactory.create(
            first_name="Other", last_name="Organizer", email="other_org@test.com"
        )
        SessionMembershipFactory.create(
            user=organizer,
            session=other_session,
            team=None,
            role=SessionMembership.ORGANIZER,
            accepted=True,
        )

        self.client.force_login(organizer)
        response = self.client.get(self.url)
        # Should get 404 because organizer doesn't have membership in current_session
        self.assertEqual(response.status_code, 404)

    def test_member_from_different_team_cannot_view(self) -> None:
        """Test that members from a different team in same session cannot view team."""
        # Create another team in same session
        other_team = Team.objects.create(
            session=self.current_session,
            project=self.project,
            name="Team Beta",
        )

        # Create user on different team
        other_team_member = UserFactory.create(
            first_name="Other", last_name="Member", email="other_member@test.com"
        )
        SessionMembershipFactory.create(
            user=other_team_member,
            session=self.current_session,
            team=other_team,
            role=SessionMembership.NAVIGATOR,
            accepted=True,
        )

        self.client.force_login(other_team_member)
        response = self.client.get(self.url)
        # Should get 403 because user is on different team
        self.assertEqual(response.status_code, 403)

    def test_team_page_shows_project_info(self) -> None:
        """Test that team page displays project information."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)
        self.assertContains(response, self.project.name)
        self.assertContains(response, self.project.url)

    def test_team_page_shows_google_drive_folder(self) -> None:
        """Test that team page displays Google Drive folder link."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)
        self.assertContains(response, self.team.google_drive_folder)
        self.assertContains(response, "Team Google Drive Folder")

    def test_team_page_shows_all_team_members(self) -> None:
        """Test that team page displays all team members."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)

        # Check captain
        self.assertContains(response, self.captain.get_full_name())
        self.assertContains(response, self.captain.email)

        # Check navigator
        self.assertContains(response, self.navigator.get_full_name())
        self.assertContains(response, self.navigator.email)

        # Check djangonauts
        self.assertContains(response, self.djangonaut1.get_full_name())
        self.assertContains(response, self.djangonaut1.email)
        self.assertContains(response, self.djangonaut2.get_full_name())
        self.assertContains(response, self.djangonaut2.email)

    def test_team_page_shows_session_status(self) -> None:
        """Test that team page displays session status."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)
        self.assertContains(response, "Active")
        self.assertContains(response, "Week 3")  # June 15 is week 3

    def test_survey_responses_visible_during_active_session(self) -> None:
        """Test that 'View Application' link is visible when session is active."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)

        # Check that "View Application" links are present for Djangonauts
        self.assertContains(response, "View Application")

        # Check that links to survey responses exist for both Djangonauts
        djangonaut1_url = reverse(
            "djangonaut_survey_response",
            kwargs={
                "session_slug": self.current_session.slug,
                "user_id": self.djangonaut1.id,
            },
        )
        self.assertContains(response, djangonaut1_url)

        djangonaut2_url = reverse(
            "djangonaut_survey_response",
            kwargs={
                "session_slug": self.current_session.slug,
                "user_id": self.djangonaut2.id,
            },
        )
        self.assertContains(response, djangonaut2_url)

    @freeze_time("2024-09-01")
    def test_survey_responses_hidden_after_session_ends(self) -> None:
        """Test that 'View Application' link is hidden after session ends."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)

        # "View Application" link should not be visible after session ends
        self.assertNotContains(response, "View Application")

        # Team info should still be visible
        self.assertContains(response, self.team.name)
        self.assertContains(response, self.project.name)

    def test_team_page_without_google_drive_folder(self) -> None:
        """Test team page when no Google Drive folder is set."""
        self.team.google_drive_folder = None
        self.team.save()

        self.client.force_login(self.captain)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Team Google Drive Folder")

    def test_declined_membership_cannot_view(self) -> None:
        """Test that users who declined membership cannot view team."""
        declined_user = UserFactory.create()
        SessionMembershipFactory.create(
            user=declined_user,
            session=self.current_session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
            accepted=False,  # Declined
        )

        self.client.force_login(declined_user)
        response = self.client.get(self.url)
        # for_user() queryset method filters to accepted memberships, so returns 404
        self.assertEqual(response.status_code, 404)

    def test_djangonaut_access_control_enforced(self) -> None:
        """Test that enforce_djangonaut_access_control is applied to team detail view."""
        self.current_session.djangonauts_have_access = False
        self.current_session.start_date = datetime(2024, 7, 1).date()
        self.current_session.save()

        self.client.force_login(self.djangonaut1)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_djangonaut_cannot_see_survey_links(self) -> None:
        """Test that Djangonauts cannot see 'View Application' links."""
        self.client.force_login(self.djangonaut1)
        response = self.client.get(self.url)

        # Djangonauts should be able to view the page
        self.assertEqual(response.status_code, 200)

        # But should not see "View Application" links
        self.assertNotContains(response, "View Application")

    def test_organizer_can_see_survey_links(self) -> None:
        """Test that Organizers can see 'View Application' links during active session."""
        # Create organizer
        organizer = UserFactory.create(
            first_name="Organizer", last_name="Admin", email="organizer@test.com"
        )
        SessionMembershipFactory.create(
            user=organizer,
            session=self.current_session,
            team=None,
            role=SessionMembership.ORGANIZER,
            accepted=True,
        )

        self.client.force_login(organizer)
        response = self.client.get(self.url)

        # Organizer should see "View Application" links
        self.assertContains(response, "View Application")

        # Check that links to survey responses exist for Djangonauts
        djangonaut1_url = reverse(
            "djangonaut_survey_response",
            kwargs={
                "session_slug": self.current_session.slug,
                "user_id": self.djangonaut1.id,
            },
        )
        self.assertContains(response, djangonaut1_url)


@freeze_time("2024-06-15")
class UserSessionListViewTests(TestCase):
    """Tests for UserSessionListView."""

    def setUp(self) -> None:
        """Set up test data."""
        super().setUp()
        self.client = Client()
        self.user = UserFactory.create()

        # Create past session (ended)
        self.past_session = SessionFactory.create(
            title="Past Session",
            start_date=datetime(2023, 1, 1).date(),
            end_date=datetime(2023, 3, 31).date(),
        )
        self.past_project = ProjectFactory.create(name="Wagtail")
        self.past_team = Team.objects.create(
            session=self.past_session, project=self.past_project, name="Past Team"
        )
        self.past_membership = SessionMembershipFactory.create(
            user=self.user,
            session=self.past_session,
            team=self.past_team,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )

        # Create current session (ongoing)
        self.current_session = SessionFactory.create(
            title="Current Session",
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 8, 30).date(),
        )
        self.current_project = ProjectFactory.create(name="Django")
        self.current_team = Team.objects.create(
            session=self.current_session,
            project=self.current_project,
            name="Current Team",
        )
        self.current_membership = SessionMembershipFactory.create(
            user=self.user,
            session=self.current_session,
            team=self.current_team,
            role=SessionMembership.NAVIGATOR,
            accepted=True,
        )

        # Create upcoming session (not yet started, ends after current)
        self.upcoming_session = SessionFactory.create(
            title="Upcoming Session",
            start_date=datetime(2025, 1, 1).date(),
            end_date=datetime(2025, 3, 31).date(),  # Ends after current
        )
        self.upcoming_project = ProjectFactory.create(name="Celery")
        self.upcoming_team = Team.objects.create(
            session=self.upcoming_session,
            project=self.upcoming_project,
            name="Upcoming Team",
        )
        self.upcoming_membership = SessionMembershipFactory.create(
            user=self.user,
            session=self.upcoming_session,
            team=self.upcoming_team,
            role=SessionMembership.CAPTAIN,
            accepted=True,
        )

        self.url = reverse("user_sessions")

    def test_anonymous_user_redirected_to_login(self) -> None:
        """Test that anonymous users are redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_user_can_view_their_sessions(self) -> None:
        """Test that authenticated user can view their sessions."""
        self.client.force_login(self.user)

        with self.assertNumQueries(12):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/session/user_sessions.html")

    def test_displays_all_user_sessions(self) -> None:
        """Test that all user's sessions are displayed."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertContains(response, self.past_session.title)
        self.assertContains(response, self.current_session.title)
        self.assertContains(response, self.upcoming_session.title)

    def test_sessions_ordered_by_end_date_desc(self) -> None:
        """Test that sessions are ordered by end date (most recent end date first)."""
        # Verify end dates are correct
        self.assertEqual(self.past_session.end_date, datetime(2023, 3, 31).date())
        self.assertEqual(self.current_session.end_date, datetime(2024, 8, 30).date())
        self.assertEqual(self.upcoming_session.end_date, datetime(2025, 3, 31).date())

        self.client.force_login(self.user)
        response = self.client.get(self.url)

        # Check the memberships are correctly retrieved
        memberships = response.context["memberships"]
        # Should be ordered by end_date desc: upcoming (2025), current (2024), past (2023)
        self.assertEqual(memberships[0].session.id, self.upcoming_session.id)
        self.assertEqual(memberships[1].session.id, self.current_session.id)
        self.assertEqual(memberships[2].session.id, self.past_session.id)

    def test_displays_role_badges(self) -> None:
        """Test that role badges are displayed correctly."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        # Check for role badges
        self.assertContains(response, "Djangonaut")  # Past session
        self.assertContains(response, "Navigator")  # Current session
        self.assertContains(response, "Captain")  # Upcoming session

    def test_displays_status_badges(self) -> None:
        """Test that status badges are displayed correctly."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertContains(response, "Completed")  # Past session
        self.assertContains(response, "Current")  # Current session
        self.assertContains(response, "Week 3")  # Current week
        self.assertContains(response, "Upcoming")  # Upcoming session

    def test_displays_team_and_project_info(self) -> None:
        """Test that team and project information is displayed."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        # Check team names
        self.assertContains(response, self.past_team.name)
        self.assertContains(response, self.current_team.name)
        self.assertContains(response, self.upcoming_team.name)

        # Check project names
        self.assertContains(response, self.past_project.name)
        self.assertContains(response, self.current_project.name)
        self.assertContains(response, self.upcoming_project.name)

    def test_displays_links_to_team_pages(self) -> None:
        """Test that links to team pages are displayed."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        past_team_url = reverse(
            "team_detail",
            kwargs={"session_slug": self.past_session.slug, "pk": self.past_team.pk},
        )
        current_team_url = reverse(
            "team_detail",
            kwargs={
                "session_slug": self.current_session.slug,
                "pk": self.current_team.pk,
            },
        )
        upcoming_team_url = reverse(
            "team_detail",
            kwargs={
                "session_slug": self.upcoming_session.slug,
                "pk": self.upcoming_team.pk,
            },
        )

        self.assertContains(response, past_team_url)
        self.assertContains(response, current_team_url)
        self.assertContains(response, upcoming_team_url)

    def test_user_with_no_sessions_sees_empty_state(self) -> None:
        """Test that user with no sessions sees appropriate message."""
        new_user = UserFactory.create()
        self.client.force_login(new_user)
        response = self.client.get(self.url)

        self.assertContains(response, "You haven't participated in any sessions yet")

    def test_membership_without_team_displays_correctly(self) -> None:
        """Test that memberships without team assignment display correctly."""
        # Create organizer without team
        organizer_session = SessionFactory.create(
            title="Organizer Session",
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 8, 30).date(),
        )
        # Create teams for the organizer session
        org_project = ProjectFactory.create(name="Test Project")
        org_team1 = Team.objects.create(
            session=organizer_session, project=org_project, name="Team One"
        )
        org_team2 = Team.objects.create(
            session=organizer_session, project=org_project, name="Team Two"
        )

        SessionMembershipFactory.create(
            user=self.user,
            session=organizer_session,
            team=None,  # No team assigned
            role=SessionMembership.ORGANIZER,
        )

        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertContains(response, organizer_session.title)
        self.assertContains(response, "Organizer")

        # Check that the organizer session shows "All Teams" section
        self.assertContains(response, "All Teams")
        self.assertContains(response, org_team1.name)
        self.assertContains(response, org_team2.name)

    def test_only_accepted_djangonaut_memberships_shown(self) -> None:
        """Test that only accepted Djangonaut memberships are shown."""
        # Create pending Djangonaut membership (should not be shown)
        pending_session = SessionFactory.create(title="Pending Session")
        SessionMembershipFactory.create(
            user=self.user,
            session=pending_session,
            role=SessionMembership.DJANGONAUT,
            accepted=None,  # Pending
        )

        # Create declined Djangonaut membership (should not be shown)
        declined_session = SessionFactory.create(title="Declined Session")
        SessionMembershipFactory.create(
            user=self.user,
            session=declined_session,
            role=SessionMembership.DJANGONAUT,
            accepted=False,  # Declined
        )

        self.client.force_login(self.user)
        response = self.client.get(self.url)

        # Should not contain pending or declined Djangonaut sessions
        self.assertNotContains(response, pending_session.title)
        self.assertNotContains(response, declined_session.title)

        # Should still contain accepted sessions
        self.assertContains(response, self.current_session.title)

    def test_non_djangonaut_roles_shown_without_acceptance(self) -> None:
        """
        Test that Captain, Navigator, and Organizer roles are shown
        regardless of accepted status.
        """
        # Create Captain membership without acceptance
        captain_session = SessionFactory.create(title="Captain Session")
        SessionMembershipFactory.create(
            user=self.user,
            session=captain_session,
            role=SessionMembership.CAPTAIN,
            accepted=None,  # Not accepted, but should still be shown
        )

        # Create Navigator membership that was declined
        navigator_session = SessionFactory.create(title="Navigator Session")
        SessionMembershipFactory.create(
            user=self.user,
            session=navigator_session,
            role=SessionMembership.NAVIGATOR,
            accepted=False,  # Declined, but should still be shown
        )

        self.client.force_login(self.user)
        response = self.client.get(self.url)

        # Non-Djangonaut roles should be shown regardless of accepted status
        self.assertContains(response, captain_session.title)
        self.assertContains(response, navigator_session.title)


@freeze_time("2024-06-15")
class DjangonautSurveyResponseViewTests(TestCase):
    """Tests for DjangonautSurveyResponseView."""

    def setUp(self) -> None:
        """Set up test data."""
        super().setUp()
        self.client = Client()

        # Create a current session (active now)
        self.current_session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 8, 30).date(),
            application_start_date=datetime(2024, 5, 1).date(),
            application_end_date=datetime(2024, 5, 31).date(),
        )

        # Create application survey
        self.survey = SurveyFactory.create(name="Application Survey")
        self.current_session.application_survey = self.survey
        self.current_session.save()

        # Create questions
        self.question1 = QuestionFactory.create(
            survey=self.survey, label="Why do you want to join?", ordering=1
        )
        self.question2 = QuestionFactory.create(
            survey=self.survey, label="What is your experience level?", ordering=2
        )

        # Create project and team
        self.project = ProjectFactory.create(name="Django")
        self.team = Team.objects.create(
            session=self.current_session,
            project=self.project,
            name="Team Alpha",
        )

        # Create users
        self.captain = UserFactory.create(
            first_name="Captain", last_name="Marvel", email="captain@test.com"
        )
        self.navigator = UserFactory.create(
            first_name="Navigator", last_name="Smith", email="navigator@test.com"
        )
        self.djangonaut = UserFactory.create(
            first_name="Django", last_name="Learner", email="djangonaut@test.com"
        )
        self.other_djangonaut = UserFactory.create(
            first_name="Other", last_name="Learner", email="other@test.com"
        )
        self.other_user = UserFactory.create(
            first_name="Outside", last_name="User", email="outside@test.com"
        )

        # Create memberships
        SessionMembershipFactory.create(
            user=self.captain,
            session=self.current_session,
            team=self.team,
            role=SessionMembership.CAPTAIN,
            accepted=True,
        )
        SessionMembershipFactory.create(
            user=self.navigator,
            session=self.current_session,
            team=self.team,
            role=SessionMembership.NAVIGATOR,
            accepted=True,
        )
        SessionMembershipFactory.create(
            user=self.djangonaut,
            session=self.current_session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )

        # Create other team with other Djangonaut
        self.other_team = Team.objects.create(
            session=self.current_session,
            project=self.project,
            name="Team Beta",
        )
        SessionMembershipFactory.create(
            user=self.other_djangonaut,
            session=self.current_session,
            team=self.other_team,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )

        # Create survey response for Djangonaut
        self.response = UserSurveyResponseFactory.create(
            user=self.djangonaut, survey=self.survey
        )
        UserQuestionResponseFactory.create(
            user_survey_response=self.response,
            question=self.question1,
            value="I want to contribute to Django",
        )
        UserQuestionResponseFactory.create(
            user_survey_response=self.response,
            question=self.question2,
            value="Intermediate",
        )

        self.url = reverse(
            "djangonaut_survey_response",
            kwargs={
                "session_slug": self.current_session.slug,
                "user_id": self.djangonaut.id,
            },
        )

    def test_anonymous_user_redirected_to_login(self) -> None:
        """Test that anonymous users are redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_captain_can_view_djangonaut_response(self) -> None:
        """Test that captains can view Djangonaut survey responses."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django Learner")
        self.assertContains(response, "I want to contribute to Django")
        self.assertContains(response, "Intermediate")

    def test_navigator_can_view_djangonaut_response(self) -> None:
        """Test that navigators can view Djangonaut survey responses."""
        self.client.force_login(self.navigator)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django Learner")
        self.assertContains(response, "I want to contribute to Django")

    def test_djangonaut_on_same_team_can_view(self) -> None:
        """Test that Djangonauts on the same team can view each other's responses."""
        # Create another Djangonaut on the same team
        teammate = UserFactory.create(
            first_name="Team", last_name="Mate", email="teammate@test.com"
        )
        SessionMembershipFactory.create(
            user=teammate,
            session=self.current_session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )

        self.client.force_login(teammate)
        response = self.client.get(self.url)
        # Djangonauts on same team can view each other's responses
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django Learner")

    def test_organizer_can_view_any_djangonaut_response(self) -> None:
        """Test that organizers can view any Djangonaut's survey response in their session."""
        # Create organizer without team assignment
        organizer = UserFactory.create(
            first_name="Organizer", last_name="Admin", email="organizer@test.com"
        )
        SessionMembershipFactory.create(
            user=organizer,
            session=self.current_session,
            team=None,  # No team assigned
            role=SessionMembership.ORGANIZER,
            accepted=True,
        )

        self.client.force_login(organizer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django Learner")
        self.assertContains(response, "I want to contribute to Django")
        self.assertContains(response, "Intermediate")

    def test_organizer_from_different_session_cannot_view(self) -> None:
        """Test that organizers from different sessions cannot view survey responses."""
        # Create a different session
        other_session = SessionFactory.create(
            start_date=datetime(2024, 9, 1).date(),
            end_date=datetime(2024, 11, 30).date(),
        )

        # Create organizer for different session
        organizer = UserFactory.create(
            first_name="Other", last_name="Organizer", email="other_org@test.com"
        )
        SessionMembershipFactory.create(
            user=organizer,
            session=other_session,
            team=None,
            role=SessionMembership.ORGANIZER,
            accepted=True,
        )

        self.client.force_login(organizer)
        response = self.client.get(self.url)
        # Should get 404 because organizer doesn't have membership in current_session
        self.assertEqual(response.status_code, 404)

    def test_member_from_different_team_cannot_view(self) -> None:
        """Test that members from different team cannot view survey responses."""
        # Create user on different team (Team Beta)
        other_team_member = UserFactory.create(
            first_name="Other", last_name="Member", email="other_member@test.com"
        )
        SessionMembershipFactory.create(
            user=other_team_member,
            session=self.current_session,
            team=self.other_team,  # Different team
            role=SessionMembership.NAVIGATOR,
            accepted=True,
        )

        self.client.force_login(other_team_member)
        response = self.client.get(self.url)
        # Should get 403 because user is on different team
        self.assertEqual(response.status_code, 403)

    def test_non_session_member_cannot_view(self) -> None:
        """Test that users not in the session cannot view responses."""
        self.client.force_login(self.other_user)
        response = self.client.get(self.url)
        # get_object_or_404 returns 404 when user has no membership in session
        self.assertEqual(response.status_code, 404)

    @freeze_time("2024-09-01")
    def test_cannot_view_after_session_ends(self) -> None:
        """Test that survey responses cannot be viewed after session ends."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_session_without_survey_returns_404(self) -> None:
        """Test that accessing a session without a survey returns 404."""
        # Remove the survey
        self.current_session.application_survey = None
        self.current_session.save()

        self.client.force_login(self.captain)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_breadcrumbs_are_present(self) -> None:
        """Test that breadcrumbs navigation is displayed."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)
        self.assertContains(response, "My Sessions")
        self.assertContains(
            response,
            reverse(
                "team_detail",
                kwargs={
                    "session_slug": self.current_session.slug,
                    "pk": self.team.pk,
                },
            ),
        )

    def test_questions_displayed_in_order(self) -> None:
        """Test that questions are displayed in the correct order."""
        self.client.force_login(self.captain)
        response = self.client.get(self.url)
        content = response.content.decode()

        # Find positions of questions in the HTML
        q1_pos = content.find(self.question1.label)
        q2_pos = content.find(self.question2.label)

        # Question 1 should appear before Question 2
        self.assertGreater(q2_pos, q1_pos)
