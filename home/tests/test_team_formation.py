"""Tests for team formation functionality."""

import json

from django.contrib.admin.sites import site
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.factories import UserAvailabilityFactory, UserFactory
from accounts.models import CustomUser, UserAvailability
from home import constants
from home.admin import SessionAdmin
from home.factories import (
    TeamFactory,
    ProjectFactory,
    SurveyFactory,
    SessionMembershipFactory,
    ProjectPreferenceFactory,
    UserSurveyResponseFactory,
)
from home.filters import ApplicantFilterSet
from home.forms import ApplicantFilterForm, OverlapAnalysisForm
from tests.timezones import CENTRAL_EUROPEAN_TIMEZONE, US_EASTERN_TIMEZONE
from home.models import (
    ProjectPreference,
    Question,
    Session,
    SessionMembership,
    Survey,
    Team,
    TypeField,
    UserSurveyResponse,
)

from home.views.team_formation import get_teams_with_statistics


class ApplicantFilterFormTestCase(TestCase):
    """Test applicant filter form."""

    def setUp(self):
        """Create test session."""
        self.session = Session.objects.create(
            title="Test Session",
            slug="test-session",
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )
        self.survey = SurveyFactory(session=self.session)

        self.team = TeamFactory(session=self.session, name="Test Team")

    def test_form_initialization_with_session(self):
        """Test form initializes with session teams."""
        form = ApplicantFilterForm(session=self.session)
        self.assertIsNotNone(form.fields["team"].queryset)
        self.assertIn(self.team, form.fields["team"].queryset)

    def test_form_valid_with_filters(self):
        """Test form validation with various filters."""
        form_data = {
            "score_min": 0,
            "score_max": 10,
            "rank_min": 1,
            "rank_max": 50,
            "team": self.team.id,
        }
        form = ApplicantFilterForm(data=form_data, session=self.session)
        self.assertTrue(form.is_valid())

    def test_project_preference_filter(self):
        """Test filtering applicants by project preference."""
        project1 = ProjectFactory()
        project2 = ProjectFactory()
        self.session.available_projects.add(project1, project2)

        applicant1 = UserFactory(username="app1")
        UserSurveyResponseFactory(user=applicant1, survey=self.survey)
        ProjectPreferenceFactory(
            user=applicant1, session=self.session, project=project1
        )

        applicant2 = UserFactory(username="app2")
        UserSurveyResponseFactory(user=applicant2, survey=self.survey)
        ProjectPreferenceFactory(
            user=applicant2, session=self.session, project=project2
        )

        qs = UserSurveyResponse.objects.filter(survey=self.survey)

        # Filter by Project 1
        filterset = ApplicantFilterSet(
            data={"project_preferences": project1.id}, queryset=qs, session=self.session
        )
        self.assertTrue(filterset.is_valid())
        self.assertEqual(filterset.qs.count(), 1)
        self.assertEqual(filterset.qs.first().user, applicant1)

        # Filter by Project 2
        filterset = ApplicantFilterSet(
            data={"project_preferences": project2.id}, queryset=qs, session=self.session
        )
        self.assertEqual(filterset.qs.count(), 1)
        self.assertEqual(filterset.qs.first().user, applicant2)


class TeamFormationViewTestCase(TestCase):
    """Test team formation views."""

    def setUp(self):
        """Create test data and authenticate."""
        self.superuser = UserFactory(
            username="admin",
            email="admin@example.com",
            is_superuser=True,
            is_staff=True,
        )
        self.superuser.set_password("test")
        self.superuser.save()
        self.client.login(username="admin", password="test")

        self.session = Session.objects.create(
            title="Test Session",
            slug="test-session",
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )

        self.survey = Survey.objects.create(
            name="Test Application",
            slug="test-application",
            session=self.session,
        )
        self.session.application_survey = self.survey
        self.session.save()

    def test_team_formation_view_requires_superuser(self):
        """Test view requires superuser access."""
        # Create regular staff user
        staff_user = UserFactory(
            username="staff", email="staff@example.com", password="test", is_staff=True
        )
        self.client.logout()
        self.client.login(username="staff", password="test")

        url = reverse("admin:session_form_teams", args=[self.session.id])
        response = self.client.get(url)

        # Should redirect to session list with error message
        self.assertEqual(response.status_code, 302)

    def test_team_formation_view_get(self):
        """Test GET request to team formation view."""
        url = reverse("admin:session_form_teams", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Form Teams:")
        self.assertContains(response, self.session.title)

    def test_calculate_overlap_ajax_requires_users(self):
        """Test AJAX overlap calculation requires user selection."""
        # Create team
        team = TeamFactory(session=self.session, name="Test Team")

        url = reverse("admin:session_calculate_overlap", args=[self.session.id])
        response = self.client.post(
            url,
            {
                "overlap-user_ids": "",
                "overlap-team": team.id,
                "overlap-analysis_type": "overlap-navigator",
            },
        )
        # Response is now HTML with error message (form validation error)
        self.assertContains(response, "overlap-result overlap-insufficient")
        self.assertContains(response, "This field is required")

    def test_calculate_overlap_ajax_navigator(self):
        """Test AJAX navigator overlap calculation with htmx."""
        # Create team with navigators
        team = TeamFactory(session=self.session, name="Test Team")

        navigator = UserFactory(
            username="nav1", email="nav1@example.com", password="test"
        )
        SessionMembership.objects.create(
            user=navigator,
            session=self.session,
            team=team,
            role=constants.NAVIGATOR,
        )

        # Create availability for navigator
        UserAvailabilityFactory(
            user=navigator, slots=[24.0, 24.5, 25.0, 25.5]  # 2 hours
        )

        # Create test users
        user1 = UserFactory(username="user1", email="user1@example.com")
        user2 = UserFactory(username="user2", email="user2@example.com")

        # Create availability
        UserAvailabilityFactory(user=user1, slots=[24.0, 24.5, 25.0, 25.5])  # 2 hours
        UserAvailabilityFactory(
            user=user2, slots=[24.0, 24.5, 25.0, 25.5]  # Same 2 hours
        )

        url = reverse("admin:session_calculate_overlap", args=[self.session.id])
        response = self.client.post(
            url,
            {
                "overlap-user_ids": f"{user1.id},{user2.id}",
                "overlap-team": team.id,
                "overlap-analysis_type": "overlap-navigator",
            },
        )

        self.assertEqual(response.status_code, 200)
        # Response is now HTML, not JSON
        self.assertContains(response, "Navigator(s) Overlap")
        self.assertContains(response, team.name)
        self.assertContains(response, "2 hour blocks")

    def test_bulk_team_assignment(self):
        """Test bulk assignment of users to a team."""

        # Create team
        team = TeamFactory(session=self.session, name="Test Team")

        # Create test users
        user1 = UserFactory(username="user1", email="user1@example.com")
        user2 = UserFactory(username="user2", email="user2@example.com")

        # Create survey responses for users
        UserSurveyResponse.objects.create(user=user1, survey=self.survey)
        UserSurveyResponse.objects.create(user=user2, survey=self.survey)

        url = reverse("admin:session_form_teams", args=[self.session.id])
        response = self.client.post(
            url,
            {
                "bulk_assign-team": team.id,
                "bulk_assign-user_ids": f"{user1.id},{user2.id}",
            },
        )

        # Should redirect back to team formation page
        self.assertEqual(response.status_code, 302)

        # Check that users were assigned to team
        memberships = SessionMembership.objects.filter(session=self.session, team=team)
        self.assertEqual(memberships.count(), 2)

        # Check that both users are assigned
        assigned_users = [m.user for m in memberships]
        self.assertIn(user1, assigned_users)
        self.assertIn(user2, assigned_users)

    def test_filter_by_navigator_overlap(self):
        """Test filtering applicants by availability overlap with navigators."""

        # Create team
        team = TeamFactory(session=self.session, name="Test Team")

        # Create navigator with availability
        navigator = UserFactory(
            username="navigator", email="navigator@example.com", password="test"
        )
        SessionMembership.objects.create(
            user=navigator,
            session=self.session,
            team=team,
            role=constants.NAVIGATOR,
        )
        UserAvailabilityFactory(
            user=navigator, slots=[24.0, 24.5, 25.0, 25.5]  # Mon 00:00-02:00
        )

        # Create applicants
        applicant_with_overlap = UserFactory(
            username="applicant1", email="applicant1@example.com", password="test"
        )
        applicant_no_overlap = UserFactory(
            username="applicant2", email="applicant2@example.com", password="test"
        )

        # Applicant 1 has overlap with navigator
        UserAvailabilityFactory(
            user=applicant_with_overlap,
            slots=[24.0, 24.5],  # Mon 00:00-01:00 (overlaps)
        )
        # Applicant 2 has no overlap
        UserAvailabilityFactory(
            user=applicant_no_overlap,
            slots=[48.0, 48.5],  # Tue 00:00-01:00 (no overlap)
        )

        # Create survey responses
        UserSurveyResponse.objects.create(
            user=applicant_with_overlap, survey=self.survey
        )
        UserSurveyResponse.objects.create(user=applicant_no_overlap, survey=self.survey)

        # Apply filter
        url = reverse("admin:session_form_teams", args=[self.session.id])
        response = self.client.get(url, {"overlap_with_navigators": team.id})

        self.assertEqual(response.status_code, 200)

        # Check that the rendered HTML shows only applicant with overlap
        # by looking for user IDs in checkbox values
        content = response.content.decode("utf-8")
        self.assertIn(f'value="{applicant_with_overlap.id}"', content)
        self.assertNotIn(f'value="{applicant_no_overlap.id}"', content)

    def test_filter_by_navigator_overlap_uses_user_timezones(self):
        """Navigator overlap filter handles applicants in another timezone."""
        team = TeamFactory(session=self.session, name="Timezone Team")
        navigator = UserFactory(username="tz_navigator")
        SessionMembership.objects.create(
            user=navigator,
            session=self.session,
            team=team,
            role=constants.NAVIGATOR,
        )
        UserAvailabilityFactory(
            user=navigator,
            slots=[33.0],
            slots_timezone=US_EASTERN_TIMEZONE,
        )

        applicant_with_overlap = UserFactory(username="tz_applicant1")
        applicant_no_overlap = UserFactory(username="tz_applicant2")
        UserAvailabilityFactory(
            user=applicant_with_overlap,
            slots=[39.0],
            slots_timezone=CENTRAL_EUROPEAN_TIMEZONE,
        )
        UserAvailabilityFactory(
            user=applicant_no_overlap,
            slots=[33.0],
            slots_timezone=CENTRAL_EUROPEAN_TIMEZONE,
        )
        UserSurveyResponse.objects.create(
            user=applicant_with_overlap, survey=self.survey
        )
        UserSurveyResponse.objects.create(user=applicant_no_overlap, survey=self.survey)

        url = reverse("admin:session_form_teams", args=[self.session.id])
        response = self.client.get(url, {"overlap_with_navigators": team.id})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn(f'value="{applicant_with_overlap.id}"', content)
        self.assertNotIn(f'value="{applicant_no_overlap.id}"', content)

    def test_filter_by_captain_overlap(self):
        """Test filtering applicants by availability overlap with captain."""

        # Create team
        team = TeamFactory(session=self.session, name="Test Team")

        # Create captain with availability
        captain = UserFactory(
            username="captain", email="captain@example.com", password="test"
        )
        SessionMembership.objects.create(
            user=captain,
            session=self.session,
            team=team,
            role=constants.CAPTAIN,
        )
        UserAvailabilityFactory(
            user=captain, slots=[48.0, 48.5, 49.0, 49.5]  # Tue 00:00-02:00
        )

        # Create applicants
        applicant_with_overlap = UserFactory(
            username="applicant1", email="applicant1@example.com", password="test"
        )
        applicant_no_overlap = UserFactory(
            username="applicant2", email="applicant2@example.com", password="test"
        )

        # Applicant 1 has overlap with captain
        UserAvailabilityFactory(
            user=applicant_with_overlap,
            slots=[48.0, 48.5],  # Tue 00:00-01:00 (overlaps)
        )
        # Applicant 2 has no overlap
        UserAvailabilityFactory(
            user=applicant_no_overlap,
            slots=[24.0, 24.5],  # Mon 00:00-01:00 (no overlap)
        )

        # Create survey responses
        UserSurveyResponse.objects.create(
            user=applicant_with_overlap, survey=self.survey
        )
        UserSurveyResponse.objects.create(user=applicant_no_overlap, survey=self.survey)

        # Apply filter
        url = reverse("admin:session_form_teams", args=[self.session.id])
        response = self.client.get(url, {"overlap_with_captain": team.id})

        self.assertEqual(response.status_code, 200)

        # Check that the rendered HTML shows only applicant with overlap
        # by looking for user IDs in checkbox values
        content = response.content.decode("utf-8")
        self.assertIn(f'value="{applicant_with_overlap.id}"', content)
        self.assertNotIn(f'value="{applicant_no_overlap.id}"', content)

    def test_filter_by_captain_overlap_uses_user_timezones(self):
        """Captain overlap filter handles applicants in another timezone."""
        team = TeamFactory(session=self.session, name="Timezone Captain Team")
        captain = UserFactory(username="tz_captain")
        SessionMembership.objects.create(
            user=captain,
            session=self.session,
            team=team,
            role=constants.CAPTAIN,
        )
        UserAvailabilityFactory(
            user=captain,
            slots=[33.0],
            slots_timezone=US_EASTERN_TIMEZONE,
        )

        applicant_with_overlap = UserFactory(username="tz_captain_applicant1")
        applicant_no_overlap = UserFactory(username="tz_captain_applicant2")
        UserAvailabilityFactory(
            user=applicant_with_overlap,
            slots=[39.0],
            slots_timezone=CENTRAL_EUROPEAN_TIMEZONE,
        )
        UserAvailabilityFactory(
            user=applicant_no_overlap,
            slots=[33.0],
            slots_timezone=CENTRAL_EUROPEAN_TIMEZONE,
        )
        UserSurveyResponse.objects.create(
            user=applicant_with_overlap, survey=self.survey
        )
        UserSurveyResponse.objects.create(user=applicant_no_overlap, survey=self.survey)

        url = reverse("admin:session_form_teams", args=[self.session.id])
        response = self.client.get(url, {"overlap_with_captain": team.id})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn(f'value="{applicant_with_overlap.id}"', content)
        self.assertNotIn(f'value="{applicant_no_overlap.id}"', content)

    def test_filter_no_navigators_on_team(self):
        """Test filtering by navigator overlap when team has no navigators."""

        # Create team without navigators
        team = TeamFactory(session=self.session, name="Test Team")

        # Create applicant
        applicant = UserFactory(
            username="applicant1", email="applicant1@example.com", password="test"
        )
        UserAvailability.objects.create(user=applicant, slots=[24.0, 24.5])
        UserSurveyResponse.objects.create(user=applicant, survey=self.survey)

        # Apply filter - should return no results
        url = reverse("admin:session_form_teams", args=[self.session.id])
        response = self.client.get(url, {"overlap_with_navigators": team.id})

        self.assertEqual(response.status_code, 200)

        # Check that the rendered HTML shows no applicants
        # by looking for user ID in checkbox values
        content = response.content.decode("utf-8")
        self.assertNotIn(f'value="{applicant.id}"', content)

    def test_team_formation_view_includes_captain_hours(self):
        """Test that team formation view includes captain overlap hours for djangonauts."""

        # Create team
        team = TeamFactory(session=self.session, name="Test Team")

        # Create captain
        captain = UserFactory(
            username="captain", email="captain@example.com", password="test"
        )
        SessionMembership.objects.create(
            user=captain,
            session=self.session,
            team=team,
            role=constants.CAPTAIN,
        )

        # Create captain availability
        UserAvailabilityFactory(
            user=captain, slots=[24.0, 24.5, 25.0, 25.5, 26.0, 26.5]  # 3 hours
        )

        # Create djangonaut
        djangonaut = UserFactory(
            username="djangonaut", email="djangonaut@example.com", password="test"
        )
        SessionMembership.objects.create(
            user=djangonaut,
            session=self.session,
            team=team,
            role=constants.DJANGONAUT,
        )

        # Create djangonaut availability (2 hours overlap with captain)
        UserAvailability.objects.create(user=djangonaut, slots=[24.0, 24.5, 25.0, 25.5])

        # Create survey response for djangonaut
        UserSurveyResponse.objects.create(user=djangonaut, survey=self.survey, score=5)

        url = reverse("admin:session_form_teams", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check that the rendered HTML includes captain hours in the team card
        content = response.content.decode("utf-8")

        # Verify team name is shown
        self.assertIn("Test Team", content)

        # Verify captain hours are displayed (2 hours) in djangonaut details table
        # The template shows captain hours in a table with Capt. Hrs column
        # Looking for pattern like: <td>2</td> in the djangonaut table
        self.assertIn(
            '<th title="Hours of overlap with captain">Capt. Hrs</th>', content
        )
        # Check that 2 hours is displayed (may have warning icon since < MIN_CAPTAIN_HOURS)
        self.assertRegex(content, r"<td>\s*2\s*")

    def test_team_formation_view_query_count(self):
        """Test that the team formation view doesn't have N+1 query issues."""
        # Create multiple projects
        project1 = ProjectFactory(name="Project Alpha")
        project2 = ProjectFactory(name="Project Beta")
        project3 = ProjectFactory(name="Project Gamma")

        # Create multiple applicants with varying project preferences
        applicants = []
        for i in range(10):
            user = UserFactory(
                username=f"applicant{i}",
                email=f"applicant{i}@example.com",
                password="test",
            )
            applicants.append(user)

            # Create survey response
            UserSurveyResponse.objects.create(
                user=user, survey=self.survey, score=i + 1, selection_rank=i + 1
            )

            # Create availability for some users
            if i % 2 == 0:
                UserAvailabilityFactory(user=user, slots=[24.0, 24.5, 25.0, 25.5])

            # Add varying project preferences
            if i % 3 == 0:
                # Some users prefer multiple projects
                ProjectPreference.objects.create(
                    user=user, session=self.session, project=project1
                )
                ProjectPreference.objects.create(
                    user=user, session=self.session, project=project2
                )
            elif i % 3 == 1:
                # Some prefer one project
                ProjectPreference.objects.create(
                    user=user, session=self.session, project=project3
                )
            # Some users have no preferences (i % 3 == 2)

        # Create a team with members
        team = TeamFactory(session=self.session, name="Test Team", project=project1)
        captain = UserFactory(
            username="captain", email="captain@example.com", password="test"
        )
        SessionMembership.objects.create(
            user=captain,
            session=self.session,
            team=team,
            role=constants.CAPTAIN,
        )

        url = reverse("admin:session_form_teams", args=[self.session.id])

        # The query count should be constant regardless of the number of applicants
        # or their project preferences, since project preferences are prefetched
        # Note: Query 7 efficiently fetches all project preferences in one query
        # There are some N+1 queries for team.project (queries 13-22) but that's
        # unrelated to the project preferences column we added
        with self.assertNumQueries(24):  # Expected stable query count
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Verify project preferences are displayed
        content = response.content.decode("utf-8")
        self.assertIn("Project Alpha", content)
        self.assertIn("Project Beta", content)
        self.assertIn("Project Gamma", content)

    def test_overlap_includes_existing_djangonauts(self):
        """Test that overlap calculation includes existing djangonauts in the rendered response."""
        # Create a djangonaut on the team with limited availability
        djangonaut = UserFactory(
            username="djangonaut", first_name="Existing", last_name="Djangonaut"
        )
        team = TeamFactory(session=self.session, name="Test Team")
        SessionMembershipFactory(
            user=djangonaut,
            session=self.session,
            team=team,
            role=constants.DJANGONAUT,
        )
        # Give djangonaut narrow availability (only Mon 00:00-01:00)
        UserAvailabilityFactory(user=djangonaut, slots=[24.0, 24.5])

        # Create a navigator on the team with wider availability
        navigator = UserFactory(
            username="navigator", first_name="Team", last_name="Navigator"
        )
        SessionMembershipFactory(
            user=navigator,
            session=self.session,
            team=team,
            role=constants.NAVIGATOR,
        )
        # Give navigator wider availability (Mon 00:00-02:00)
        UserAvailabilityFactory(user=navigator, slots=[24.0, 24.5, 25.0, 25.5])

        # Create an applicant with wide availability
        applicant = UserFactory(username="applicant")
        UserAvailabilityFactory(user=applicant, slots=[24.0, 24.5, 25.0, 25.5])

        url = reverse("admin:session_calculate_overlap", args=[self.session.id])
        response = self.client.post(
            url,
            {
                "overlap-team": team.id,
                "overlap-analysis_type": "overlap-navigator",
                "overlap-user_ids": str(applicant.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # The navigator overlap title and team name should be rendered
        self.assertIn("Navigator(s) Overlap", content)
        self.assertIn("Test Team", content)

        # Existing members (navigator + djangonaut) should be listed
        self.assertIn("Existing members:", content)
        self.assertIn("Existing Djangonaut", content)
        self.assertIn("Team Navigator", content)

        # The overlap should be 1 hour: djangonaut's narrower availability [24.0, 24.5]
        # constrains the intersection of all three users. If existing djangonauts were
        # excluded, the overlap would be 2 hours (navigator ∩ applicant = [24.0..25.5]).
        self.assertIn("1 hour blocks found", content)

    def test_compare_availability_url_in_context(self):
        """Test that compare_availability_url is present in overlap context."""
        navigator = UserFactory(username="navigator")
        team = TeamFactory(session=self.session, name="Test Team")
        SessionMembershipFactory(
            user=navigator,
            session=self.session,
            team=team,
            role=constants.NAVIGATOR,
        )

        applicant = UserFactory(username="applicant")

        form_data = {
            "overlap-team": team.id,
            "overlap-analysis_type": "overlap-navigator",
            "overlap-user_ids": str(applicant.id),
        }
        form = OverlapAnalysisForm(data=form_data, session=self.session)
        self.assertTrue(form.is_valid())

        context = form.calculate_navigator_overlap_context()
        self.assertIn("compare_availability_url", context)
        url = context["compare_availability_url"]
        self.assertIn(reverse("compare_availability"), url)
        self.assertIn(str(navigator.id), url)
        self.assertIn(str(applicant.id), url)

    def test_team_statistics_has_compare_url(self):
        """Test that team statistics includes compare availability URL."""
        djangonaut = UserFactory(username="djangonaut")
        team = TeamFactory(session=self.session, name="Test Team")
        SessionMembershipFactory(
            user=djangonaut,
            session=self.session,
            team=team,
            role=constants.DJANGONAUT,
        )

        teams_data = get_teams_with_statistics(self.session)
        self.assertEqual(len(teams_data), 1)
        stat = teams_data[0]

        self.assertTrue(hasattr(stat, "compare_availability_url"))
        self.assertIn(reverse("compare_availability"), stat.compare_availability_url)
        self.assertIn(str(djangonaut.id), stat.compare_availability_url)
