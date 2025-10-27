"""Tests for Survey admin copy functionality and CSV export."""

import csv
import io
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from home.admin import SurveyAdmin
from home.models import (
    Survey,
    Question,
    Session,
    UserSurveyResponse,
    UserQuestionResponse,
)
from home.models.survey import TypeField


User = get_user_model()


class SurveyAdminCopyTest(TestCase):
    """Test the copy_survey admin action."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="test"
        )

        cls.session = Session.objects.create(
            title="Test Session 2025",
            slug="test-session-2025",
            start_date="2025-01-01",
            end_date="2025-06-01",
            invitation_date="2024-12-01",
            application_start_date="2024-11-01",
            application_end_date="2024-12-15",
        )

        cls.survey = Survey.objects.create(
            name="Test Survey",
            description="A test survey",
            session=cls.session,
        )

        Question.objects.create(
            survey=cls.survey,
            label="Email question",
            type_field=TypeField.EMAIL,
            ordering=1,
        )
        Question.objects.create(
            survey=cls.survey,
            label="Rating question",
            type_field=TypeField.RATING,
            choices="5",
            ordering=2,
        )

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.admin = SurveyAdmin(Survey, AdminSite())

    def test_copy_survey_with_questions(self):
        """Test copying survey creates new survey with all questions."""
        request = self.factory.post("/admin/home/survey/")
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        SessionMiddleware(MessageMiddleware(lambda r: None))

        queryset = Survey.objects.filter(pk=self.survey.pk)
        self.admin.copy_survey(request, queryset)

        copied = Survey.objects.exclude(pk=self.survey.pk).first()

        self.assertEqual(
            copied.name, f"Test Survey (Copied - {timezone.now().date().isoformat()})"
        )
        self.assertIsNone(copied.session)
        self.assertEqual(copied.questions.count(), 2)
        self.assertEqual(
            list(copied.questions.values_list("label", flat=True)),
            ["Email question", "Rating question"],
        )
        self.assertEqual(Question.objects.all().count(), 4)


class SurveyCSVExportTest(TestCase):
    """Test the CSV export with scorers functionality."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="test"
        )

        cls.respondent1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            first_name="John",
            last_name="Doe",
        )
        cls.respondent2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            first_name="Jane",
            last_name="Smith",
        )

        cls.session = Session.objects.create(
            title="Test Session 2025",
            slug="test-session-2025",
            start_date="2025-01-01",
            end_date="2025-06-01",
            invitation_date="2024-12-01",
            application_start_date="2024-11-01",
            application_end_date="2024-12-15",
        )

        cls.survey = Survey.objects.create(
            name="Test Survey",
            description="A test survey",
            session=cls.session,
        )

        cls.question1 = Question.objects.create(
            survey=cls.survey,
            label="What is your email?",
            type_field=TypeField.EMAIL,
            ordering=1,
        )
        cls.question2 = Question.objects.create(
            survey=cls.survey,
            label="Rate your experience",
            type_field=TypeField.RATING,
            choices="5",
            ordering=2,
        )
        cls.question3 = Question.objects.create(
            survey=cls.survey,
            label="Tell us about yourself",
            type_field=TypeField.TEXT_AREA,
            ordering=3,
        )

        # Create survey responses
        cls.response1 = UserSurveyResponse.objects.create(
            survey=cls.survey,
            user=cls.respondent1,
        )
        UserQuestionResponse.objects.create(
            question=cls.question1,
            user_survey_response=cls.response1,
            value="john@example.com",
        )
        UserQuestionResponse.objects.create(
            question=cls.question2,
            user_survey_response=cls.response1,
            value="5",
        )
        UserQuestionResponse.objects.create(
            question=cls.question3,
            user_survey_response=cls.response1,
            value="I am a Django developer with 5 years of experience.",
        )

        cls.response2 = UserSurveyResponse.objects.create(
            survey=cls.survey,
            user=cls.respondent2,
        )
        UserQuestionResponse.objects.create(
            question=cls.question1,
            user_survey_response=cls.response2,
            value="jane@example.com",
        )
        UserQuestionResponse.objects.create(
            question=cls.question2,
            user_survey_response=cls.response2,
            value="4",
        )
        UserQuestionResponse.objects.create(
            question=cls.question3,
            user_survey_response=cls.response2,
            value="I am interested in contributing to open source.",
        )

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.admin = SurveyAdmin(Survey, AdminSite())
        self.client.login(username="admin", password="test")

    def test_export_csv_view_get(self):
        """Test GET request shows the form."""
        url = reverse("admin:survey_export_csv", args=[self.survey.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Export Survey Responses")
        self.assertContains(response, "Scorer Names")

    def test_export_to_csv_action_single_survey(self):
        """Test admin action redirects to export form for single survey."""
        request = self.factory.post("/admin/home/survey/")
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = Survey.objects.filter(pk=self.survey.pk)
        response = self.admin.export_to_csv_with_scorers(request, queryset)

        expected_url = reverse("admin:survey_export_csv", args=[self.survey.id])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, expected_url)

    def test_export_to_csv_action_multiple_surveys(self):
        """Test admin action shows error for multiple surveys."""
        survey2 = Survey.objects.create(
            name="Another Survey",
            description="Another test survey",
        )

        request = self.factory.post("/admin/home/survey/")
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = Survey.objects.filter(pk__in=[self.survey.pk, survey2.pk])
        response = self.admin.export_to_csv_with_scorers(request, queryset)

        # Should return None and add error message
        self.assertIsNone(response)

    def test_export_csv_view_returns_csv(self):
        """Test admin CSV export view returns CSV file."""
        url = reverse("admin:survey_export_csv", args=[self.survey.id])
        response = self.client.post(url, {"scorer_names": ""})

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn(
            f"survey_{self.survey.slug}_responses.csv", response["Content-Disposition"]
        )
