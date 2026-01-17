import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from home.admin import (
    UserSurveyResponseAdmin,
    WaitlistStatusFilter,
    SelectionStatusFilter,
)
from home.factories import (
    SessionFactory,
    SessionMembershipFactory,
    SurveyFactory,
    UserSurveyResponseFactory,
    WaitlistFactory,
)
from home.models import SessionMembership, UserSurveyResponse

User = get_user_model()


@pytest.fixture
def admin_site():
    """Return an AdminSite instance."""
    return AdminSite()


@pytest.fixture
def request_factory():
    """Return a RequestFactory instance."""
    return RequestFactory()


@pytest.fixture
def mock_request(request_factory):
    """Return a mock request object."""
    request = request_factory.get("/admin/home/usersurveyresponse/")
    request.user = User.objects.create_superuser(
        username="admin", email="admin@example.com", password="password"
    )
    return request


@pytest.fixture
def model_admin(admin_site):
    """Return a UserSurveyResponseAdmin instance."""
    return UserSurveyResponseAdmin(UserSurveyResponse, admin_site)


@pytest.mark.django_db
class TestWaitlistStatusFilter:
    """Tests for the WaitlistStatusFilter."""

    def test_filter_lookups(self, model_admin, mock_request):
        """Test that the filter provides correct lookup options."""
        filter_instance = WaitlistStatusFilter(
            mock_request,
            {},
            UserSurveyResponse,
            model_admin,
        )
        lookups = filter_instance.lookups(mock_request, model_admin)

        assert lookups == (
            ("yes", "Waitlisted"),
            ("no", "Not Waitlisted"),
        )

    def test_filter_shows_waitlisted_users(self, model_admin, mock_request):
        """Test that the filter correctly shows only waitlisted users."""
        session = SessionFactory()
        survey = SurveyFactory()
        session.application_survey = survey
        session.save()

        waitlisted_response = UserSurveyResponseFactory(survey=survey)
        non_waitlisted_response = UserSurveyResponseFactory(survey=survey)

        WaitlistFactory(user=waitlisted_response.user, session=session)

        # Note: Django admin filters expect params values to be lists (from QueryDict)
        filter_instance = WaitlistStatusFilter(
            mock_request,
            {"waitlisted": ["yes"]},
            UserSurveyResponse,
            model_admin,
        )
        queryset = UserSurveyResponse.objects.all()
        filtered_queryset = filter_instance.queryset(mock_request, queryset)

        # Should only return the waitlisted response
        assert filtered_queryset.count() == 1
        assert waitlisted_response in filtered_queryset
        assert non_waitlisted_response not in filtered_queryset

    def test_filter_shows_non_waitlisted_users(self, model_admin, mock_request):
        """Test that the filter correctly shows only non-waitlisted users."""
        session = SessionFactory()
        survey = SurveyFactory()
        session.application_survey = survey
        session.save()

        waitlisted_response = UserSurveyResponseFactory(survey=survey)
        non_waitlisted_response = UserSurveyResponseFactory(survey=survey)

        WaitlistFactory(user=waitlisted_response.user, session=session)

        filter_instance = WaitlistStatusFilter(
            mock_request,
            {"waitlisted": ["no"]},
            UserSurveyResponse,
            model_admin,
        )
        queryset = UserSurveyResponse.objects.all()
        filtered_queryset = filter_instance.queryset(mock_request, queryset)

        # Should only return the non-waitlisted response
        assert filtered_queryset.count() == 1
        assert non_waitlisted_response in filtered_queryset
        assert waitlisted_response not in filtered_queryset

    def test_filter_no_value_returns_all(self, model_admin, mock_request):
        """Test that filter returns all results when no value is selected."""
        session = SessionFactory()
        survey = SurveyFactory()
        session.application_survey = survey
        session.save()

        UserSurveyResponseFactory(survey=survey)
        UserSurveyResponseFactory(survey=survey)

        filter_instance = WaitlistStatusFilter(
            mock_request,
            {},
            UserSurveyResponse,
            model_admin,
        )
        queryset = UserSurveyResponse.objects.all()
        filtered_queryset = filter_instance.queryset(mock_request, queryset)

        # Should return all responses
        assert filtered_queryset.count() == 2


@pytest.mark.django_db
class TestSelectionStatusFilter:
    """Tests for the SelectionStatusFilter."""

    def test_filter_lookups(self, model_admin, mock_request):
        """Test that the filter provides correct lookup options."""
        filter_instance = SelectionStatusFilter(
            mock_request,
            {},
            UserSurveyResponse,
            model_admin,
        )
        lookups = filter_instance.lookups(mock_request, model_admin)

        assert lookups == (
            ("yes", "Selected"),
            ("no", "Not Selected"),
        )

    def test_filter_shows_selected_users(self, model_admin, mock_request):
        """Test that the filter correctly shows only selected users."""
        session = SessionFactory()
        survey = SurveyFactory()
        session.application_survey = survey
        session.save()

        selected_response = UserSurveyResponseFactory(survey=survey)
        non_selected_response = UserSurveyResponseFactory(survey=survey)

        SessionMembershipFactory(
            user=selected_response.user,
            session=session,
            role=SessionMembership.DJANGONAUT,
        )

        filter_instance = SelectionStatusFilter(
            mock_request,
            {"selected": ["yes"]},
            UserSurveyResponse,
            model_admin,
        )
        queryset = UserSurveyResponse.objects.all()
        filtered_queryset = filter_instance.queryset(mock_request, queryset)

        # Should only return the selected response
        assert filtered_queryset.count() == 1
        assert selected_response in filtered_queryset
        assert non_selected_response not in filtered_queryset

    def test_filter_shows_non_selected_users(self, model_admin, mock_request):
        """Test that the filter correctly shows only non-selected users."""
        session = SessionFactory()
        survey = SurveyFactory()
        session.application_survey = survey
        session.save()

        selected_response = UserSurveyResponseFactory(survey=survey)
        non_selected_response = UserSurveyResponseFactory(survey=survey)

        SessionMembershipFactory(
            user=selected_response.user,
            session=session,
            role=SessionMembership.DJANGONAUT,
        )

        filter_instance = SelectionStatusFilter(
            mock_request,
            {"selected": ["no"]},
            UserSurveyResponse,
            model_admin,
        )
        queryset = UserSurveyResponse.objects.all()
        filtered_queryset = filter_instance.queryset(mock_request, queryset)

        # Should only return the non-selected response
        assert filtered_queryset.count() == 1
        assert non_selected_response in filtered_queryset
        assert selected_response not in filtered_queryset

    def test_filter_no_value_returns_all(self, model_admin, mock_request):
        """Test that filter returns all results when no value is selected."""
        session = SessionFactory()
        survey = SurveyFactory()
        session.application_survey = survey
        session.save()

        UserSurveyResponseFactory(survey=survey)
        UserSurveyResponseFactory(survey=survey)

        filter_instance = SelectionStatusFilter(
            mock_request,
            {},
            UserSurveyResponse,
            model_admin,
        )
        queryset = UserSurveyResponse.objects.all()
        filtered_queryset = filter_instance.queryset(mock_request, queryset)

        # Should return all responses
        assert filtered_queryset.count() == 2
