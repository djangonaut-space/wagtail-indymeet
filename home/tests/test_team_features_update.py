from django.test import TestCase, RequestFactory
from django.urls import reverse
from accounts.factories import UserFactory, UserAvailabilityFactory
from home.factories import TeamFactory, ProjectFactory
from home.models import (
    Session,
    SessionMembership,
    ProjectPreference,
    UserSurveyResponse,
    Survey,
)
from home.forms import OverlapAnalysisForm
from home.views.team_formation import get_teams_with_statistics
from home.filters import ApplicantFilterSet


class TeamFeaturesUpdateTestCase(TestCase):
    def setUp(self):
        self.session = Session.objects.create(
            title="Test Session",
            slug="test-session",
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )
        self.survey = Survey.objects.create(name="Test Survey", session=self.session)
        self.session.application_survey = self.survey
        self.session.save()
        self.team = TeamFactory(session=self.session, name="Test Team")

    def test_overlap_includes_existing_djangonauts(self):
        """Test that overlap calculation includes existing djangonauts."""
        # Create a djangonaut on the team
        djangonaut = UserFactory(username="djangonaut")
        SessionMembership.objects.create(
            user=djangonaut,
            session=self.session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
        )
        # Give djangonaut availability (slot 24.0 = Mon 00:00)
        UserAvailabilityFactory(user=djangonaut, slots=[24.0, 24.5])

        # Create a navigator on the team
        navigator = UserFactory(username="navigator")
        SessionMembership.objects.create(
            user=navigator,
            session=self.session,
            team=self.team,
            role=SessionMembership.NAVIGATOR,
        )
        # Give navigator availability (slot 24.0 = Mon 00:00)
        UserAvailabilityFactory(user=navigator, slots=[24.0, 24.5])

        # Create an applicant with matching availability
        applicant = UserFactory(username="applicant")
        UserAvailabilityFactory(user=applicant, slots=[24.0, 24.5])

        # We need "selected_users" for the form. The form uses cleaned_data['user_ids']
        # But for testing `calculate_navigator_overlap_context` we can mock or use valid data

        form_data = {
            "overlap-team": self.team.id,
            "overlap-analysis_type": "overlap-navigator",
            "overlap-user_ids": str(applicant.id),
        }
        form = OverlapAnalysisForm(data=form_data, session=self.session)
        self.assertTrue(form.is_valid())

        context = form.calculate_navigator_overlap_context()

        # Check that existing djangonauts are in context
        self.assertIn("existing_djangonauts", context)
        self.assertEqual(len(context["existing_djangonauts"]), 1)
        self.assertEqual(context["existing_djangonauts"][0], djangonaut)

        # Check overlap calculation (should be 1 hour because all 3 overlap)
        # The overlap logic calculates intersection of ALL users.
        # Navigator and Djangonaut and Applicant all have [24.0, 24.5].
        self.assertEqual(context["hour_blocks"], 1)

    def test_compare_availability_url_in_context(self):
        """Test that compare_availability_url is present in overlap context."""
        navigator = UserFactory(username="navigator")
        SessionMembership.objects.create(
            user=navigator,
            session=self.session,
            team=self.team,
            role=SessionMembership.NAVIGATOR,
        )

        applicant = UserFactory(username="applicant")

        form_data = {
            "overlap-team": self.team.id,
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
        SessionMembership.objects.create(
            user=djangonaut,
            session=self.session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
        )

        teams_data = get_teams_with_statistics(self.session)
        self.assertEqual(len(teams_data), 1)
        stat = teams_data[0]

        self.assertTrue(hasattr(stat, "compare_availability_url"))
        self.assertIn(reverse("compare_availability"), stat.compare_availability_url)
        self.assertIn(str(djangonaut.id), stat.compare_availability_url)

    def test_project_preference_filter(self):
        """Test filtering applicants by project preference."""
        project1 = ProjectFactory(name="Project 1")
        project2 = ProjectFactory(name="Project 2")
        self.session.available_projects.add(project1, project2)

        applicant1 = UserFactory(username="app1")
        UserSurveyResponse.objects.create(user=applicant1, survey=self.survey)
        ProjectPreference.objects.create(
            user=applicant1, session=self.session, project=project1
        )

        applicant2 = UserFactory(username="app2")
        UserSurveyResponse.objects.create(user=applicant2, survey=self.survey)
        ProjectPreference.objects.create(
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
