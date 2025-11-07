"""Tests for waitlist filters in ApplicantFilterSet."""

from django.test import TestCase

from accounts.factories import UserFactory
from home.factories import SessionFactory, SurveyFactory
from home.filters import ApplicantFilterSet
from home.models import UserSurveyResponse, Waitlist


class WaitlistFilterTestCase(TestCase):
    """Test waitlist filtering in ApplicantFilterSet."""

    def setUp(self):
        """Create test data."""
        self.session = SessionFactory()
        self.survey = SurveyFactory(session=self.session)
        self.session.application_survey = self.survey
        self.session.save()

        # Create users
        self.user1 = UserFactory(username="user1")
        self.user2 = UserFactory(username="user2")
        self.user3 = UserFactory(username="user3")
        self.user4 = UserFactory(username="user4")

        # Create survey responses
        self.response1 = UserSurveyResponse.objects.create(
            user=self.user1, survey=self.survey
        )
        self.response2 = UserSurveyResponse.objects.create(
            user=self.user2, survey=self.survey
        )
        self.response3 = UserSurveyResponse.objects.create(
            user=self.user3, survey=self.survey
        )
        self.response4 = UserSurveyResponse.objects.create(
            user=self.user4, survey=self.survey
        )

        # Add user1 and user2 to waitlist
        Waitlist.objects.create(user=self.user1, session=self.session)
        Waitlist.objects.create(user=self.user2, session=self.session)

        # user3 and user4 are not waitlisted

    def test_exclude_waitlisted_filter(self):
        """Test that exclude_waitlisted filter hides waitlisted users."""
        queryset = UserSurveyResponse.objects.filter(survey=self.survey)

        filterset = ApplicantFilterSet(
            data={"exclude_waitlisted": True},
            queryset=queryset,
            session=self.session,
        )

        filtered_qs = filterset.qs
        user_ids = [response.user_id for response in filtered_qs]

        # Should only include user3 and user4 (not waitlisted)
        self.assertIn(self.user3.id, user_ids)
        self.assertIn(self.user4.id, user_ids)
        self.assertNotIn(self.user1.id, user_ids)
        self.assertNotIn(self.user2.id, user_ids)

    def test_show_waitlisted_only_filter(self):
        """Test that show_waitlisted_only filter shows only waitlisted users."""
        queryset = UserSurveyResponse.objects.filter(survey=self.survey)

        filterset = ApplicantFilterSet(
            data={"show_waitlisted_only": True},
            queryset=queryset,
            session=self.session,
        )

        filtered_qs = filterset.qs
        user_ids = [response.user_id for response in filtered_qs]

        # Should only include user1 and user2 (waitlisted)
        self.assertIn(self.user1.id, user_ids)
        self.assertIn(self.user2.id, user_ids)
        self.assertNotIn(self.user3.id, user_ids)
        self.assertNotIn(self.user4.id, user_ids)

    def test_no_waitlist_filter_applied(self):
        """Test that without filters, all users are shown."""
        queryset = UserSurveyResponse.objects.filter(survey=self.survey)

        filterset = ApplicantFilterSet(
            data={},
            queryset=queryset,
            session=self.session,
        )

        filtered_qs = filterset.qs
        user_ids = [response.user_id for response in filtered_qs]

        # Should include all users
        self.assertIn(self.user1.id, user_ids)
        self.assertIn(self.user2.id, user_ids)
        self.assertIn(self.user3.id, user_ids)
        self.assertIn(self.user4.id, user_ids)

    def test_exclude_waitlisted_with_false_value(self):
        """Test that exclude_waitlisted=False doesn't filter anything."""
        queryset = UserSurveyResponse.objects.filter(survey=self.survey)

        filterset = ApplicantFilterSet(
            data={"exclude_waitlisted": False},
            queryset=queryset,
            session=self.session,
        )

        filtered_qs = filterset.qs
        user_ids = [response.user_id for response in filtered_qs]

        # Should include all users
        self.assertEqual(len(user_ids), 4)

    def test_show_waitlisted_only_with_false_value(self):
        """Test that show_waitlisted_only=False doesn't filter anything."""
        queryset = UserSurveyResponse.objects.filter(survey=self.survey)

        filterset = ApplicantFilterSet(
            data={"show_waitlisted_only": False},
            queryset=queryset,
            session=self.session,
        )

        filtered_qs = filterset.qs
        user_ids = [response.user_id for response in filtered_qs]

        # Should include all users
        self.assertEqual(len(user_ids), 4)

    def test_filters_work_with_different_sessions(self):
        """Test that waitlist filters only apply to the current session."""
        # Create another session
        session2 = SessionFactory()
        survey2 = SurveyFactory(session=session2)
        session2.application_survey = survey2
        session2.save()

        # Create response for user1 in session2
        UserSurveyResponse.objects.create(user=self.user1, survey=survey2)

        # Add user1 to session2 waitlist (they're already in session1 waitlist)
        Waitlist.objects.create(user=self.user1, session=session2)

        # Filter session2 responses
        queryset = UserSurveyResponse.objects.filter(survey=survey2)

        filterset = ApplicantFilterSet(
            data={"show_waitlisted_only": True},
            queryset=queryset,
            session=session2,
        )

        filtered_qs = filterset.qs
        user_ids = [response.user_id for response in filtered_qs]

        # Should only include user1 for session2
        self.assertIn(self.user1.id, user_ids)
        self.assertEqual(len(user_ids), 1)
