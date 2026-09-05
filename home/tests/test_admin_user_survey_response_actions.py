"""Tests for UserSurveyResponseAdmin admin actions."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from accounts.factories import UserFactory
from home.admin import UserSurveyResponseAdmin
from home.factories import SurveyFactory, UserSurveyResponseFactory
from home.models import UserSurveyResponse


class UserSurveyResponseAdminActionsTests(TestCase):
    """Tests for the evaluate_tutorial_submission_action admin action."""

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
        """Create a request with session and messages support."""
        request = self.factory.post("/admin/home/usersurveyresponse/")
        request.user = self.superuser

        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        messages = FallbackStorage(request)
        setattr(request, "_messages", messages)

        return request

    @patch("home.admin.evaluate_tutorial_submission_now")
    def test_queues_evaluation_for_each_selected_response(self, mock_task):
        """The action enqueues one evaluation per selected survey response."""
        survey = SurveyFactory(session=None)
        response1 = UserSurveyResponseFactory(survey=survey)
        response2 = UserSurveyResponseFactory(survey=survey)

        request = self._get_request()
        queryset = UserSurveyResponse.objects.filter(
            id__in=[response1.id, response2.id]
        )
        self.admin.evaluate_tutorial_submission_action(request, queryset)

        self.assertEqual(mock_task.enqueue.call_count, 2)
        enqueued_ids = {
            call.kwargs["user_survey_response_id"]
            for call in mock_task.enqueue.call_args_list
        }
        self.assertEqual(enqueued_ids, {response1.id, response2.id})
