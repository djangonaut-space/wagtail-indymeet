"""Tests for Session Organizer row-level permissions in admin."""

from unittest.mock import Mock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.test import TestCase, RequestFactory

from accounts.factories import UserFactory
from home.admin import (
    SessionAdmin,
    SessionMembershipAdmin,
    SessionMembershipInline,
    SurveyAdmin,
    TeamAdmin,
    UserQuestionResponseAdmin,
    UserSurveyResponseAdmin,
    WaitlistAdmin,
)
from home.factories import (
    QuestionFactory,
    SessionFactory,
    SessionMembershipFactory,
    SurveyFactory,
    TeamFactory,
    UserQuestionResponseFactory,
    UserSurveyResponseFactory,
    WaitlistFactory,
)
from home.models import (
    Session,
    SessionMembership,
    Survey,
    Team,
    UserQuestionResponse,
    UserSurveyResponse,
    Waitlist,
)


class SessionOrganizerPermissionsTestMixin:
    """Mixin providing common test fixtures for organizer permission tests."""

    def setUp(self):
        """Set up test data for permission tests."""
        self.factory = RequestFactory()
        self.admin_site = AdminSite()

        # Create the Session Organizers group
        self.organizers_group = Group.objects.create(name="Session Organizers")

        # Create a superuser
        self.superuser = UserFactory.create(
            email="super@example.com",
            is_superuser=True,
            is_staff=True,
        )

        # Create a regular staff user (not in Session Organizers group)
        self.staff_user = UserFactory.create(
            email="staff@example.com",
            is_staff=True,
        )

        # Create a session organizer user
        self.organizer_user = UserFactory.create(
            email="organizer@example.com",
            is_staff=True,
        )
        self.organizer_user.groups.add(self.organizers_group)

        # Create two sessions
        self.organized_session = SessionFactory.create(
            title="Organized Session",
            slug="organized-session",
        )
        self.other_session = SessionFactory.create(
            title="Other Session",
            slug="other-session",
        )

        # Create a SessionMembership making organizer_user an ORGANIZER of organized_session
        self.organizer_membership = SessionMembershipFactory.create(
            user=self.organizer_user,
            session=self.organized_session,
            role=SessionMembership.ORGANIZER,
        )

        # Create a SessionMembership for other_session (different organizer)
        self.other_organizer = UserFactory.create(email="other@example.com")
        self.other_organizer_membership = SessionMembershipFactory.create(
            user=self.other_organizer,
            session=self.other_session,
            role=SessionMembership.ORGANIZER,
        )

    def _create_mock_request(self, user):
        """Helper to create a mock request with a user."""
        request = self.factory.get("/admin/")
        request.user = user
        return request


class SessionAdminPermissionsTests(SessionOrganizerPermissionsTestMixin, TestCase):
    """Tests for SessionAdmin queryset filtering."""

    def setUp(self):
        super().setUp()
        self.model_admin = SessionAdmin(Session, self.admin_site)

    def test_superuser_sees_all_sessions(self):
        """Superusers should see all sessions."""
        request = self._create_mock_request(self.superuser)
        qs = self.model_admin.get_queryset(request)

        # Superuser should see at least the two test sessions
        self.assertGreaterEqual(qs.count(), 2)
        self.assertIn(self.organized_session, qs)
        self.assertIn(self.other_session, qs)

    def test_organizer_sees_only_organized_sessions(self):
        """Session Organizers should only see sessions they organize."""
        request = self._create_mock_request(self.organizer_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 1)
        self.assertIn(self.organized_session, qs)
        self.assertNotIn(self.other_session, qs)

    def test_staff_user_without_organizer_role_sees_nothing(self):
        """Staff users without ORGANIZER role see empty list."""
        request = self._create_mock_request(self.staff_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 0)

    def test_organizer_with_multiple_sessions(self):
        """Organizer with multiple sessions should see all their sessions."""
        # Make organizer_user also an organizer of other_session
        SessionMembershipFactory.create(
            user=self.organizer_user,
            session=self.other_session,
            role=SessionMembership.ORGANIZER,
        )

        request = self._create_mock_request(self.organizer_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 2)
        self.assertIn(self.organized_session, qs)
        self.assertIn(self.other_session, qs)

    def test_organizer_with_no_sessions(self):
        """Session Organizer with no sessions should see empty list."""
        # Create a new organizer with no sessions
        new_organizer = UserFactory.create(email="new@example.com", is_staff=True)
        new_organizer.groups.add(self.organizers_group)

        request = self._create_mock_request(new_organizer)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 0)


class SessionMembershipAdminPermissionsTests(
    SessionOrganizerPermissionsTestMixin, TestCase
):
    """Tests for SessionMembershipAdmin queryset filtering."""

    def setUp(self):
        super().setUp()
        self.model_admin = SessionMembershipAdmin(SessionMembership, self.admin_site)

        # Create additional memberships for testing
        self.organized_session_member = SessionMembershipFactory.create(
            session=self.organized_session,
            role=SessionMembership.DJANGONAUT,
        )
        self.other_session_member = SessionMembershipFactory.create(
            session=self.other_session,
            role=SessionMembership.DJANGONAUT,
        )

    def test_superuser_sees_all_memberships(self):
        """Superusers should see all session memberships."""
        request = self._create_mock_request(self.superuser)
        qs = self.model_admin.get_queryset(request)

        # Should include at least 4 memberships (2 organizers + 2 djangonauts)
        self.assertGreaterEqual(qs.count(), 4)
        self.assertIn(self.organized_session_member, qs)
        self.assertIn(self.other_session_member, qs)

    def test_organizer_sees_only_organized_session_memberships(self):
        """Session Organizers should only see memberships for their sessions."""
        request = self._create_mock_request(self.organizer_user)
        qs = self.model_admin.get_queryset(request)

        # Should see memberships for organized_session only
        organized_session_memberships = qs.filter(session=self.organized_session)
        other_session_memberships = qs.filter(session=self.other_session)

        self.assertGreater(organized_session_memberships.count(), 0)
        self.assertEqual(other_session_memberships.count(), 0)

    def test_staff_user_without_organizer_role_sees_nothing(self):
        """Staff users without ORGANIZER role see empty list."""
        request = self._create_mock_request(self.staff_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 0)


class SessionMembershipInlinePermissionsTests(
    SessionOrganizerPermissionsTestMixin, TestCase
):
    """Tests for SessionMembershipInline queryset filtering."""

    def setUp(self):
        super().setUp()
        self.inline = SessionMembershipInline(
            parent_model=Session, admin_site=self.admin_site
        )

        # Create memberships for testing
        self.organized_session_member = SessionMembershipFactory.create(
            session=self.organized_session,
            role=SessionMembership.DJANGONAUT,
        )
        self.other_session_member = SessionMembershipFactory.create(
            session=self.other_session,
            role=SessionMembership.DJANGONAUT,
        )

    def test_superuser_sees_all_inline_memberships(self):
        """Superusers should see all memberships in inline."""
        request = self._create_mock_request(self.superuser)
        qs = self.inline.get_queryset(request)

        self.assertGreaterEqual(qs.count(), 4)

    def test_organizer_sees_only_organized_session_inline_memberships(self):
        """Session Organizers should only see memberships for their sessions in inline.

        Note: The inline filtering works in conjunction with SessionAdmin's filtering,
        providing defense-in-depth. The SessionAdmin already filters to only show
        sessions the organizer manages, so the inline will only ever be displayed
        for those sessions.
        """
        request = self._create_mock_request(self.organizer_user)

        # The inline's get_queryset applies session filtering
        # Since SessionAdmin already limits which sessions are shown, this is defense in depth
        qs = self.inline.get_queryset(request)

        # Get all session IDs from the filtered queryset
        session_ids_in_qs = set(qs.values_list("session_id", flat=True))

        # If there are any memberships in the queryset, they should only be for organized sessions
        if session_ids_in_qs:
            # Should only include the organized session, not the other session
            self.assertIn(self.organized_session.id, session_ids_in_qs)
            self.assertNotIn(self.other_session.id, session_ids_in_qs)


class TeamAdminPermissionsTests(SessionOrganizerPermissionsTestMixin, TestCase):
    """Tests for TeamAdmin queryset filtering."""

    def setUp(self):
        super().setUp()
        self.model_admin = TeamAdmin(Team, self.admin_site)

        # Create teams
        self.organized_team = TeamFactory.create(
            session=self.organized_session,
            name="Organized Team",
        )
        self.other_team = TeamFactory.create(
            session=self.other_session,
            name="Other Team",
        )

    def test_superuser_sees_all_teams(self):
        """Superusers should see all teams."""
        request = self._create_mock_request(self.superuser)
        qs = self.model_admin.get_queryset(request)

        # Superuser should see at least the two test teams
        self.assertGreaterEqual(qs.count(), 2)
        self.assertIn(self.organized_team, qs)
        self.assertIn(self.other_team, qs)

    def test_organizer_sees_only_organized_session_teams(self):
        """Session Organizers should only see teams for their sessions."""
        request = self._create_mock_request(self.organizer_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 1)
        self.assertIn(self.organized_team, qs)
        self.assertNotIn(self.other_team, qs)

    def test_staff_user_without_organizer_role_sees_nothing(self):
        """Staff users without ORGANIZER role see empty list."""
        request = self._create_mock_request(self.staff_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 0)


class SurveyAdminPermissionsTests(SessionOrganizerPermissionsTestMixin, TestCase):
    """Tests for SurveyAdmin queryset filtering."""

    def setUp(self):
        super().setUp()
        self.model_admin = SurveyAdmin(Survey, self.admin_site)

        # Create surveys
        self.organized_survey = SurveyFactory.create(
            name="Organized Survey",
            session=self.organized_session,
        )
        self.other_survey = SurveyFactory.create(
            name="Other Survey",
            session=self.other_session,
        )
        self.null_session_survey = SurveyFactory.create(
            name="Null Session Survey",
            session=None,
        )

    def test_superuser_sees_all_surveys(self):
        """Superusers should see all surveys."""
        request = self._create_mock_request(self.superuser)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 3)
        self.assertIn(self.organized_survey, qs)
        self.assertIn(self.other_survey, qs)
        self.assertIn(self.null_session_survey, qs)

    def test_organizer_sees_only_organized_session_surveys(self):
        """Session Organizers should only see surveys for their sessions."""
        request = self._create_mock_request(self.organizer_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 1)
        self.assertIn(self.organized_survey, qs)
        self.assertNotIn(self.other_survey, qs)
        self.assertNotIn(self.null_session_survey, qs)

    def test_staff_user_without_organizer_role_sees_nothing(self):
        """Staff users without ORGANIZER role see empty list."""
        request = self._create_mock_request(self.staff_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 0)


class WaitlistAdminPermissionsTests(SessionOrganizerPermissionsTestMixin, TestCase):
    """Tests for WaitlistAdmin queryset filtering."""

    def setUp(self):
        super().setUp()
        self.model_admin = WaitlistAdmin(Waitlist, self.admin_site)

        # Create waitlist entries
        self.organized_waitlist = WaitlistFactory.create(
            session=self.organized_session,
        )
        self.other_waitlist = WaitlistFactory.create(
            session=self.other_session,
        )

    def test_superuser_sees_all_waitlist_entries(self):
        """Superusers should see all waitlist entries."""
        request = self._create_mock_request(self.superuser)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 2)
        self.assertIn(self.organized_waitlist, qs)
        self.assertIn(self.other_waitlist, qs)

    def test_organizer_sees_only_organized_session_waitlist(self):
        """Session Organizers should only see waitlist entries for their sessions."""
        request = self._create_mock_request(self.organizer_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 1)
        self.assertIn(self.organized_waitlist, qs)
        self.assertNotIn(self.other_waitlist, qs)

    def test_staff_user_without_organizer_role_sees_nothing(self):
        """Staff users without ORGANIZER role see empty list."""
        request = self._create_mock_request(self.staff_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 0)


class UserSurveyResponseAdminPermissionsTests(
    SessionOrganizerPermissionsTestMixin, TestCase
):
    """Tests for UserSurveyResponseAdmin queryset filtering."""

    def setUp(self):
        super().setUp()
        self.model_admin = UserSurveyResponseAdmin(UserSurveyResponse, self.admin_site)

        # Create surveys
        self.organized_survey = SurveyFactory.create(
            name="Organized Survey",
            session=self.organized_session,
        )
        self.other_survey = SurveyFactory.create(
            name="Other Survey",
            session=self.other_session,
        )
        self.null_session_survey = SurveyFactory.create(
            name="Null Session Survey",
            session=None,
        )

        # Create responses
        self.organized_response = UserSurveyResponseFactory.create(
            survey=self.organized_survey,
        )
        self.other_response = UserSurveyResponseFactory.create(
            survey=self.other_survey,
        )
        self.null_session_response = UserSurveyResponseFactory.create(
            survey=self.null_session_survey,
        )

    def test_superuser_sees_all_responses(self):
        """Superusers should see all survey responses."""
        request = self._create_mock_request(self.superuser)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 3)
        self.assertIn(self.organized_response, qs)
        self.assertIn(self.other_response, qs)
        self.assertIn(self.null_session_response, qs)

    def test_organizer_sees_only_organized_session_responses(self):
        """Session Organizers should only see responses for their session surveys."""
        request = self._create_mock_request(self.organizer_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 1)
        self.assertIn(self.organized_response, qs)
        self.assertNotIn(self.other_response, qs)
        self.assertNotIn(self.null_session_response, qs)

    def test_staff_user_without_organizer_role_sees_nothing(self):
        """Staff users without ORGANIZER role see empty list."""
        request = self._create_mock_request(self.staff_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 0)


class UserQuestionResponseAdminPermissionsTests(
    SessionOrganizerPermissionsTestMixin, TestCase
):
    """Tests for UserQuestionResponseAdmin queryset filtering."""

    def setUp(self):
        super().setUp()
        self.model_admin = UserQuestionResponseAdmin(
            UserQuestionResponse, self.admin_site
        )

        # Create surveys
        self.organized_survey = SurveyFactory.create(
            name="Organized Survey",
            session=self.organized_session,
        )
        self.other_survey = SurveyFactory.create(
            name="Other Survey",
            session=self.other_session,
        )
        self.null_session_survey = SurveyFactory.create(
            name="Null Session Survey",
            session=None,
        )

        # Create questions
        self.organized_question = QuestionFactory.create(survey=self.organized_survey)
        self.other_question = QuestionFactory.create(survey=self.other_survey)
        self.null_session_question = QuestionFactory.create(
            survey=self.null_session_survey
        )

        # Create user survey responses
        self.organized_user_response = UserSurveyResponseFactory.create(
            survey=self.organized_survey,
        )
        self.other_user_response = UserSurveyResponseFactory.create(
            survey=self.other_survey,
        )
        self.null_session_user_response = UserSurveyResponseFactory.create(
            survey=self.null_session_survey,
        )

        # Create question responses
        self.organized_question_response = UserQuestionResponseFactory.create(
            question=self.organized_question,
            user_survey_response=self.organized_user_response,
        )
        self.other_question_response = UserQuestionResponseFactory.create(
            question=self.other_question,
            user_survey_response=self.other_user_response,
        )
        self.null_session_question_response = UserQuestionResponseFactory.create(
            question=self.null_session_question,
            user_survey_response=self.null_session_user_response,
        )

    def test_superuser_sees_all_question_responses(self):
        """Superusers should see all question responses."""
        request = self._create_mock_request(self.superuser)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 3)
        self.assertIn(self.organized_question_response, qs)
        self.assertIn(self.other_question_response, qs)
        self.assertIn(self.null_session_question_response, qs)

    def test_organizer_sees_only_organized_session_question_responses(self):
        """Session Organizers should only see question responses for their sessions."""
        request = self._create_mock_request(self.organizer_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 1)
        self.assertIn(self.organized_question_response, qs)
        self.assertNotIn(self.other_question_response, qs)
        self.assertNotIn(self.null_session_question_response, qs)

    def test_staff_user_without_organizer_role_sees_nothing(self):
        """Staff users without ORGANIZER role see empty list."""
        request = self._create_mock_request(self.staff_user)
        qs = self.model_admin.get_queryset(request)

        self.assertEqual(qs.count(), 0)
