"""Tests for custom QuerySet methods."""

from django.test import TestCase

from accounts.factories import UserAvailabilityFactory, UserFactory
from home.factories import (
    SessionFactory,
    SessionMembershipFactory,
    SurveyFactory,
    TeamFactory,
    UserSurveyResponseFactory,
)
from home.models import SessionMembership, UserSurveyResponse


class UserSurveyResponseQuerySetTestCase(TestCase):
    """Test UserSurveyResponseQuerySet methods."""

    def setUp(self):
        """Create test data using factories."""
        self.session = SessionFactory(
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )

        self.survey = SurveyFactory(session=self.session)
        self.session.application_survey = self.survey
        self.session.save()

        # Create previous survey
        self.previous_survey = SurveyFactory(session=self.session)

        # Create users
        self.user1 = UserFactory()
        self.user2 = UserFactory()
        self.user3 = UserFactory()

        # Create team
        self.team = TeamFactory(session=self.session)

    def test_for_survey(self):
        """Test filtering responses by survey."""
        response1 = UserSurveyResponseFactory(user=self.user1, survey=self.survey)
        UserSurveyResponseFactory(user=self.user2, survey=self.previous_survey)

        qs = UserSurveyResponse.objects.for_survey(self.survey)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), response1)

    def test_with_previous_application_stats(self):
        """Test annotation with previous application statistics."""
        # Create previous sessions with application surveys
        previous_session1 = SessionFactory(
            start_date="2023-06-01", end_date="2023-12-31"
        )
        previous_app_survey1 = SurveyFactory(session=previous_session1)
        previous_session1.application_survey = previous_app_survey1
        previous_session1.save()

        previous_session2 = SessionFactory(
            start_date="2024-06-01", end_date="2024-12-31"
        )
        previous_app_survey2 = SurveyFactory(session=previous_session2)
        previous_session2.application_survey = previous_app_survey2
        previous_session2.save()

        # Create previous applications on different surveys
        UserSurveyResponseFactory(user=self.user1, survey=previous_app_survey1, score=5)
        UserSurveyResponseFactory(user=self.user1, survey=previous_app_survey2, score=7)

        # Create current application
        response = UserSurveyResponseFactory(user=self.user1, survey=self.survey)

        # Query with annotations
        qs = UserSurveyResponse.objects.filter(
            id=response.id
        ).with_previous_application_stats(self.survey)
        result = qs.first()

        self.assertEqual(result.annotated_previous_application_count, 2)
        self.assertEqual(result.annotated_previous_avg_score_value, 6.0)

    def test_with_previous_application_stats_no_previous(self):
        """Test annotation when user has no previous applications."""
        response = UserSurveyResponseFactory(user=self.user1, survey=self.survey)

        qs = UserSurveyResponse.objects.filter(
            id=response.id
        ).with_previous_application_stats(self.survey)
        result = qs.first()

        self.assertEqual(result.annotated_previous_application_count, 0)
        self.assertIsNone(result.annotated_previous_avg_score_value)

    def test_with_availability_check(self):
        """Test annotation with availability check."""
        # User with availability
        UserAvailabilityFactory(user=self.user1, slots=[24.0, 24.5])
        response1 = UserSurveyResponseFactory(user=self.user1, survey=self.survey)

        # User without availability
        response2 = UserSurveyResponseFactory(user=self.user2, survey=self.survey)

        # User with empty availability
        UserAvailabilityFactory(user=self.user3, slots=[])
        response3 = UserSurveyResponseFactory(user=self.user3, survey=self.survey)

        qs = UserSurveyResponse.objects.with_availability_check()

        result1 = qs.get(id=response1.id)
        result2 = qs.get(id=response2.id)
        result3 = qs.get(id=response3.id)

        self.assertTrue(result1.annotated_has_availability)
        self.assertFalse(result2.annotated_has_availability)
        self.assertFalse(result3.annotated_has_availability)

    def test_with_session_memberships(self):
        """Test prefetching session memberships."""
        response = UserSurveyResponseFactory(user=self.user1, survey=self.survey)
        SessionMembershipFactory(
            user=self.user1,
            session=self.session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
        )

        qs = UserSurveyResponse.objects.filter(id=response.id).with_session_memberships(
            self.session
        )
        result = qs.first()

        # Check prefetched data is accessible
        self.assertTrue(hasattr(result.user, "prefetched_current_session_memberships"))
        self.assertEqual(len(result.user.prefetched_current_session_memberships), 1)
        self.assertEqual(
            result.user.prefetched_current_session_memberships[0].team, self.team
        )

    def test_with_team_assignment(self):
        """Test filtering by team assignment."""
        response1 = UserSurveyResponseFactory(user=self.user1, survey=self.survey)
        response2 = UserSurveyResponseFactory(user=self.user2, survey=self.survey)

        # Assign user1 to team
        SessionMembershipFactory(
            user=self.user1,
            session=self.session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
        )

        qs = UserSurveyResponse.objects.with_team_assignment(self.team, self.session)

        self.assertEqual(qs.count(), 1)
        self.assertIn(response1, qs)
        self.assertNotIn(response2, qs)

    def test_without_team_assignment(self):
        """Test filtering users without team assignment."""
        response1 = UserSurveyResponseFactory(user=self.user1, survey=self.survey)
        response2 = UserSurveyResponseFactory(user=self.user2, survey=self.survey)
        response3 = UserSurveyResponseFactory(user=self.user3, survey=self.survey)

        # Assign user1 to team
        SessionMembershipFactory(
            user=self.user1,
            session=self.session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
        )

        # Create membership for user2 but without team
        SessionMembershipFactory(
            user=self.user2,
            session=self.session,
            team=None,
            role=SessionMembership.DJANGONAUT,
        )

        qs = UserSurveyResponse.objects.without_team_assignment(self.session)

        self.assertEqual(qs.count(), 2)
        self.assertNotIn(response1, qs)
        self.assertIn(response2, qs)
        self.assertIn(response3, qs)

    def test_with_availability_overlap(self):
        """Test filtering by availability overlap."""
        # Create users with different availability
        UserAvailabilityFactory(
            user=self.user1, slots=[24.0, 24.5, 25.0, 25.5]  # Mon 00:00-02:00
        )
        UserAvailabilityFactory(
            user=self.user2, slots=[48.0, 48.5, 49.0, 49.5]  # Tue 00:00-02:00
        )

        response1 = UserSurveyResponseFactory(user=self.user1, survey=self.survey)
        response2 = UserSurveyResponseFactory(user=self.user2, survey=self.survey)

        # Test overlap with Monday slots
        qs = UserSurveyResponse.objects.with_availability_overlap([24.0, 24.5])

        self.assertEqual(qs.count(), 1)
        self.assertIn(response1, qs)
        self.assertNotIn(response2, qs)

    def test_with_availability_overlap_empty_slots(self):
        """Test filtering with empty slots returns no results."""
        UserSurveyResponseFactory(user=self.user1, survey=self.survey)

        qs = UserSurveyResponse.objects.with_availability_overlap([])

        self.assertEqual(qs.count(), 0)

    def test_with_navigator_overlap(self):
        """Test filtering by navigator overlap."""
        # Create navigator with availability
        navigator = UserFactory()
        SessionMembershipFactory(
            user=navigator,
            session=self.session,
            team=self.team,
            role=SessionMembership.NAVIGATOR,
        )
        UserAvailabilityFactory(
            user=navigator, slots=[24.0, 24.5, 25.0, 25.5]  # Mon 00:00-02:00
        )

        # Create applicants
        UserAvailabilityFactory(user=self.user1, slots=[24.0, 24.5])  # Overlaps
        UserAvailabilityFactory(user=self.user2, slots=[48.0, 48.5])  # No overlap

        response1 = UserSurveyResponseFactory(user=self.user1, survey=self.survey)
        response2 = UserSurveyResponseFactory(user=self.user2, survey=self.survey)

        qs = UserSurveyResponse.objects.with_navigator_overlap(self.team)

        self.assertEqual(qs.count(), 1)
        self.assertIn(response1, qs)
        self.assertNotIn(response2, qs)

    def test_with_navigator_overlap_no_navigators(self):
        """Test filtering when team has no navigators."""
        UserSurveyResponseFactory(user=self.user1, survey=self.survey)

        qs = UserSurveyResponse.objects.with_navigator_overlap(self.team)

        self.assertEqual(qs.count(), 0)

    def test_with_captain_overlap(self):
        """Test filtering by captain overlap."""
        # Create captain with availability
        captain = UserFactory()
        SessionMembershipFactory(
            user=captain,
            session=self.session,
            team=self.team,
            role=SessionMembership.CAPTAIN,
        )
        UserAvailabilityFactory(
            user=captain, slots=[48.0, 48.5, 49.0, 49.5]  # Tue 00:00-02:00
        )

        # Create applicants
        UserAvailabilityFactory(user=self.user1, slots=[48.0, 48.5])  # Overlaps
        UserAvailabilityFactory(user=self.user2, slots=[24.0, 24.5])  # No overlap

        response1 = UserSurveyResponseFactory(user=self.user1, survey=self.survey)
        response2 = UserSurveyResponseFactory(user=self.user2, survey=self.survey)

        qs = UserSurveyResponse.objects.with_captain_overlap(self.team)

        self.assertEqual(qs.count(), 1)
        self.assertIn(response1, qs)
        self.assertNotIn(response2, qs)

    def test_with_captain_overlap_no_captain(self):
        """Test filtering when team has no captain."""
        UserSurveyResponseFactory(user=self.user1, survey=self.survey)

        qs = UserSurveyResponse.objects.with_captain_overlap(self.team)

        self.assertEqual(qs.count(), 0)

    def test_with_full_team_formation_data(self):
        """Test combined annotation for team formation."""
        # Create previous session with its own application survey
        previous_session = SessionFactory(
            start_date="2024-06-01",
            end_date="2024-12-31",
        )
        previous_application_survey = SurveyFactory(session=previous_session)
        previous_session.application_survey = previous_application_survey
        previous_session.save()

        # Create previous application
        UserSurveyResponseFactory(
            user=self.user1, survey=previous_application_survey, score=5
        )

        # Create availability
        UserAvailabilityFactory(user=self.user1, slots=[24.0, 24.5])

        # Create current application
        response = UserSurveyResponseFactory(user=self.user1, survey=self.survey)

        # Create membership
        SessionMembershipFactory(
            user=self.user1,
            session=self.session,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
        )

        qs = UserSurveyResponse.objects.with_full_team_formation_data(self.session)

        self.assertEqual(qs.count(), 1)
        result = qs.first()

        # Check all annotations are present
        self.assertEqual(result.annotated_previous_application_count, 1)
        self.assertEqual(result.annotated_previous_avg_score_value, 5.0)
        self.assertTrue(result.annotated_has_availability)
        self.assertTrue(hasattr(result.user, "prefetched_current_session_memberships"))

    def test_with_full_team_formation_data_no_survey(self):
        """Test with_full_team_formation_data with no application survey."""
        session_no_survey = SessionFactory(
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )

        qs = UserSurveyResponse.objects.with_full_team_formation_data(session_no_survey)

        self.assertEqual(qs.count(), 0)
