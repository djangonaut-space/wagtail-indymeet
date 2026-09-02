import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from home.admin import TutorialEvaluationAdmin, TutorialEvaluationSessionFilter
from home.factories import SessionFactory, SurveyFactory, UserSurveyResponseFactory
from home.models import TutorialEvaluation

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
