"""Tests for UserSurveyResponseAdmin list display columns."""

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from accounts.factories import UserFactory
from home.admin import UserSurveyResponseAdmin
from home.factories import (
    ProjectFactory,
    ProjectPreferenceFactory,
    SessionFactory,
    SurveyFactory,
    UserSurveyResponseFactory,
)
from home.models import UserSurveyResponse


class UserSurveyResponseAdminProjectPreferencesTests(TestCase):
    """Tests for the project_preferences admin display method."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = UserSurveyResponseAdmin(UserSurveyResponse, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com",
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_superuser=True,
        )

    def _get_request(self):
        request = self.factory.get("/admin/home/usersurveyresponse/")
        request.user = self.superuser
        return request

    def test_shows_preferences_in_selection_order(self):
        """The column lists a respondent's chosen projects, comma separated."""
        survey = SurveyFactory(session=None)
        session = SessionFactory.create(application_survey=survey)
        user = UserFactory.create()
        response = UserSurveyResponseFactory(survey=survey, user=user)

        project_a = ProjectFactory.create(name="Project A")
        project_b = ProjectFactory.create(name="Project B")
        ProjectPreferenceFactory.create(user=user, session=session, project=project_a)
        ProjectPreferenceFactory.create(user=user, session=session, project=project_b)

        obj = self.admin.get_queryset(self._get_request()).get(pk=response.pk)
        self.assertEqual(self.admin.project_preferences(obj), "Project A, Project B")

    def test_shows_any_project_when_no_preferences(self):
        """A respondent with no ProjectPreference rows is okay with any project."""
        survey = SurveyFactory(session=None)
        SessionFactory.create(application_survey=survey)
        response = UserSurveyResponseFactory(survey=survey)

        obj = self.admin.get_queryset(self._get_request()).get(pk=response.pk)
        self.assertEqual(self.admin.project_preferences(obj), "Any project")

    def test_blank_when_survey_has_no_session(self):
        """The column is empty when the survey isn't tied to an application session."""
        survey = SurveyFactory(session=None)
        response = UserSurveyResponseFactory(survey=survey)

        obj = self.admin.get_queryset(self._get_request()).get(pk=response.pk)
        self.assertEqual(self.admin.project_preferences(obj), "")
