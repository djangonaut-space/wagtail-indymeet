"""Tests for BulkTeamAssignmentForm project preference validation."""

from django.test import TestCase

from accounts.factories import UserFactory
from home.factories import ProjectFactory, SessionFactory, SurveyFactory, TeamFactory
from home.forms import BulkTeamAssignmentForm
from home.models import ProjectPreference, Team, UserSurveyResponse


class BulkTeamAssignmentFormTestCase(TestCase):
    """Test BulkTeamAssignmentForm validation with project preferences."""

    def setUp(self):
        """Create test data."""
        self.session = SessionFactory()
        self.survey = SurveyFactory(session=self.session)
        self.session.application_survey = self.survey
        self.session.save()

        # Create projects
        self.project_django = ProjectFactory(name="Django")
        self.project_wagtail = ProjectFactory(name="Wagtail")

        # Add projects to session
        self.session.available_projects.add(self.project_django, self.project_wagtail)

        # Create teams (using TeamFactory)
        self.django_team = TeamFactory(
            session=self.session, name="Django Team", project=self.project_django
        )
        self.wagtail_team = TeamFactory(
            session=self.session, name="Wagtail Team", project=self.project_wagtail
        )

        # Create users
        self.user1 = UserFactory(username="user1")
        self.user2 = UserFactory(username="user2")
        self.user3 = UserFactory(username="user3")

        # Create survey responses
        UserSurveyResponse.objects.create(user=self.user1, survey=self.survey)
        UserSurveyResponse.objects.create(user=self.user2, survey=self.survey)
        UserSurveyResponse.objects.create(user=self.user3, survey=self.survey)

    def test_valid_assignment_users_with_matching_preferences(self):
        """Test that users with matching project preferences can be assigned."""
        # User1 and User2 prefer Django
        ProjectPreference.objects.create(
            user=self.user1, session=self.session, project=self.project_django
        )
        ProjectPreference.objects.create(
            user=self.user2, session=self.session, project=self.project_django
        )

        form = BulkTeamAssignmentForm(
            data={
                "bulk_assign-user_ids": f"{self.user1.id},{self.user2.id}",
                "bulk_assign-team": self.django_team.id,
            },
            session=self.session,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_valid_assignment_users_with_no_preferences(self):
        """Test that users with no preferences can be assigned to any team."""
        # User1 has no preferences
        form = BulkTeamAssignmentForm(
            data={
                "bulk_assign-user_ids": f"{self.user1.id}",
                "bulk_assign-team": self.django_team.id,
            },
            session=self.session,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_assignment_user_with_conflicting_preference(self):
        """Test that users with conflicting project preferences cannot be assigned."""
        # User1 prefers Wagtail but trying to assign to Django team
        ProjectPreference.objects.create(
            user=self.user1, session=self.session, project=self.project_wagtail
        )

        form = BulkTeamAssignmentForm(
            data={
                "bulk_assign-user_ids": f"{self.user1.id}",
                "bulk_assign-team": self.django_team.id,
            },
            session=self.session,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("team", form.errors)
        error_message = form.errors["team"][0]
        self.assertIn(self.user1.get_full_name(), error_message)
        self.assertIn("Django", error_message)
        self.assertIn(
            "Users with no preferences can be assigned to any project", error_message
        )

    def test_invalid_assignment_multiple_users_with_conflicts(self):
        """Test error message when multiple users have conflicting preferences."""
        # User1 prefers Wagtail
        ProjectPreference.objects.create(
            user=self.user1, session=self.session, project=self.project_wagtail
        )
        # User2 prefers Wagtail
        ProjectPreference.objects.create(
            user=self.user2, session=self.session, project=self.project_wagtail
        )

        form = BulkTeamAssignmentForm(
            data={
                "bulk_assign-user_ids": f"{self.user1.id},{self.user2.id}",
                "bulk_assign-team": self.django_team.id,
            },
            session=self.session,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("team", form.errors)
        error_message = form.errors["team"][0]

        # Should mention both users
        self.assertIn(self.user1.get_full_name(), error_message)
        self.assertIn(self.user2.get_full_name(), error_message)

    def test_nonexistent_user_ids(self):
        """Test validation when user IDs don't exist."""
        form = BulkTeamAssignmentForm(
            data={
                "bulk_assign-user_ids": "99999,88888",
                "bulk_assign-team": self.django_team.id,
            },
            session=self.session,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("user_ids", form.errors)
        self.assertIn("do not exist", form.errors["user_ids"][0])
