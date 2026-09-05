from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.test import RequestFactory, override_settings
from django.utils import timezone

from home.admin import TutorialEvaluationAdmin, TutorialEvaluationSessionFilter
from home.factories import SessionFactory, SurveyFactory, UserSurveyResponseFactory
from home.models import TutorialEvaluation
from home.preview_email import tutorial_reminder_email_action

User = get_user_model()


@pytest.fixture
def admin_site():
    return AdminSite()


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def mock_request(request_factory):
    request = request_factory.get("/admin/home/tutorialevaluation/")
    request.user = User.objects.create_superuser(
        username="admin", email="admin@example.com", password="password"
    )
    return request


@pytest.fixture
def model_admin(admin_site):
    return TutorialEvaluationAdmin(TutorialEvaluation, admin_site)


@pytest.mark.django_db
class TestTutorialEvaluationSessionFilter:
    def test_filter_shows_evaluations_for_selected_session(
        self, model_admin, mock_request
    ):
        session = SessionFactory()
        survey = SurveyFactory()
        session.application_survey = survey
        session.save()

        other_session = SessionFactory()
        other_survey = SurveyFactory()
        other_session.application_survey = other_survey
        other_session.save()

        matching_response = UserSurveyResponseFactory(survey=survey)
        other_response = UserSurveyResponseFactory(survey=other_survey)

        matching_evaluation = TutorialEvaluation.objects.create(
            user_survey_response=matching_response
        )
        other_evaluation = TutorialEvaluation.objects.create(
            user_survey_response=other_response
        )

        filter_instance = TutorialEvaluationSessionFilter(
            mock_request,
            {"session": [str(session.id)]},
            TutorialEvaluation,
            model_admin,
        )
        queryset = TutorialEvaluation.objects.all()
        filtered_queryset = filter_instance.queryset(mock_request, queryset)

        assert filtered_queryset.count() == 1
        assert matching_evaluation in filtered_queryset
        assert other_evaluation not in filtered_queryset

    def test_filter_no_value_returns_all(self, model_admin, mock_request):
        response = UserSurveyResponseFactory(survey=SurveyFactory(session=None))
        TutorialEvaluation.objects.create(user_survey_response=response)

        filter_instance = TutorialEvaluationSessionFilter(
            mock_request,
            {},
            TutorialEvaluation,
            model_admin,
        )
        queryset = TutorialEvaluation.objects.all()
        filtered_queryset = filter_instance.queryset(mock_request, queryset)

        assert filtered_queryset.count() == 1


@pytest.mark.django_db
class TestTutorialEvaluationAdmin:
    def test_list_filter_includes_result(self, model_admin):
        assert "result" in model_admin.list_filter

    def test_search_by_user_email(self, model_admin, mock_request):
        response = UserSurveyResponseFactory(survey=SurveyFactory(session=None))
        evaluation = TutorialEvaluation.objects.create(user_survey_response=response)

        queryset, _ = model_admin.get_search_results(
            mock_request, TutorialEvaluation.objects.all(), response.user.email
        )

        assert list(queryset) == [evaluation]

    def test_tutorial_link_opens_in_new_window(self, model_admin):
        response = UserSurveyResponseFactory(survey=SurveyFactory(session=None))
        evaluation = TutorialEvaluation.objects.create(
            user_survey_response=response,
            link="https://github.com/alex/django/tree/ticket_1",
        )

        rendered = model_admin.tutorial_link(evaluation)

        assert 'target="_blank"' in rendered
        assert 'href="https://github.com/alex/django/tree/ticket_1"' in rendered

    def test_tutorial_link_blank_when_no_link(self, model_admin):
        response = UserSurveyResponseFactory(survey=SurveyFactory(session=None))
        evaluation = TutorialEvaluation.objects.create(user_survey_response=response)

        assert model_admin.tutorial_link(evaluation) == ""


@pytest.mark.django_db
class TestTutorialEvaluationAdminActions:
    """Tests for the admin actions on TutorialEvaluationAdmin."""

    def _post_request(self, request_factory, user):
        request = request_factory.post("/admin/home/tutorialevaluation/")
        request.user = user

        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        messages = FallbackStorage(request)
        setattr(request, "_messages", messages)

        return request

    @patch("home.admin.send_tutorial_reminder_now")
    def test_send_tutorial_reminder_action_queues_each_selected(
        self, mock_task, model_admin, request_factory
    ):
        admin_user = User.objects.create_superuser(
            username="admin2", email="admin2@example.com", password="password"
        )
        response1 = UserSurveyResponseFactory(survey=SurveyFactory(session=None))
        response2 = UserSurveyResponseFactory(survey=SurveyFactory(session=None))
        evaluation1 = TutorialEvaluation.objects.create(user_survey_response=response1)
        evaluation2 = TutorialEvaluation.objects.create(user_survey_response=response2)

        request = self._post_request(request_factory, admin_user)
        queryset = TutorialEvaluation.objects.filter(
            id__in=[evaluation1.id, evaluation2.id]
        )
        model_admin.send_tutorial_reminder_action(request, queryset)

        assert mock_task.enqueue.call_count == 2
        enqueued_ids = {
            call.kwargs["evaluation_id"] for call in mock_task.enqueue.call_args_list
        }
        assert enqueued_ids == {evaluation1.id, evaluation2.id}

    @override_settings(ENVIRONMENT="production", BASE_URL="https://djangonaut.space")
    def test_preview_reminder_email_action_sends_to_admin(
        self, model_admin, request_factory
    ):
        admin_user = User.objects.create_superuser(
            username="admin3", email="admin3@example.com", password="password"
        )
        session = SessionFactory(short_name="Session 9")
        survey = SurveyFactory(session=session)
        response = UserSurveyResponseFactory(survey=survey)
        evaluation = TutorialEvaluation.objects.create(
            user_survey_response=response,
            result=-1,
            evaluated_at=timezone.now(),
        )

        request = self._post_request(request_factory, admin_user)
        queryset = TutorialEvaluation.objects.filter(id=evaluation.id)
        tutorial_reminder_email_action(model_admin, request, queryset)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["admin3@example.com"]
