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


class UserSurveyResponseAdminInterviewActionsTests(TestCase):
    """Tests for the record captain/navigator interview admin actions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = UserSurveyResponseAdmin(UserSurveyResponse, AdminSite())
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.survey = SurveyFactory(session=None)
        self.response = UserSurveyResponseFactory(survey=self.survey)
        self.other_response = UserSurveyResponseFactory(survey=self.survey)

    def _get_request(self):
        """Create a request with session and messages support."""
        request = self.factory.post("/admin/home/usersurveyresponse/")
        request.user = self.superuser

        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_record_interview_actions_update_selected_users_profiles(self):
        """Each action sets its flag only on profiles of the selected responses."""
        cases = [
            ("mark_passed_captain_interview", "passed_captain_interview", True),
            ("mark_failed_captain_interview", "passed_captain_interview", False),
            ("mark_passed_navigator_interview", "passed_navigator_interview", True),
            ("mark_failed_navigator_interview", "passed_navigator_interview", False),
        ]
        for action, field, expected in cases:
            with self.subTest(action=action):
                request = self._get_request()
                queryset = UserSurveyResponse.objects.filter(id=self.response.id)

                getattr(self.admin, action)(request, queryset)

                profile = self.response.user.profile
                other_profile = self.other_response.user.profile
                profile.refresh_from_db()
                other_profile.refresh_from_db()
                self.assertIs(getattr(profile, field), expected)
                self.assertIsNone(getattr(other_profile, field))
                self.assertEqual(
                    [str(m) for m in request._messages],
                    [
                        f"Updated {field.replace('_', ' ')} to {expected} "
                        "for 1 profile(s)."
                    ],
                )

    def test_record_interview_counts_each_profile_once(self):
        """Multiple responses from one user update and count a single profile."""
        second_survey = SurveyFactory(session=None)
        duplicate = UserSurveyResponseFactory(
            survey=second_survey, user=self.response.user
        )
        request = self._get_request()
        queryset = UserSurveyResponse.objects.filter(
            id__in=[self.response.id, duplicate.id]
        )

        self.admin.mark_passed_captain_interview(request, queryset)

        self.response.user.profile.refresh_from_db()
        self.assertIs(self.response.user.profile.passed_captain_interview, True)
        self.assertEqual(
            [str(m) for m in request._messages],
            ["Updated passed captain interview to True for 1 profile(s)."],
        )
