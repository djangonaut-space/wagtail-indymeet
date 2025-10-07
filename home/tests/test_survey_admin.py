"""Tests for Survey admin copy functionality."""

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone

from home.admin import SurveyAdmin
from home.models import Survey, Question, Session
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
