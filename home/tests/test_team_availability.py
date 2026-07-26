"""Tests for team-formation specific availability overlap logic."""

from django.test import TestCase

from accounts.factories import UserFactory
from availability.factories import UserAvailabilityFactory
from home.team_availability import calculate_team_overlap


class CalculateTeamOverlapTestCase(TestCase):
    """Test team overlap calculation."""

    def setUp(self):
        """Create test users with availability."""
        self.user1 = UserFactory(username="user1", email="user1@example.com")
        self.user2 = UserFactory(username="user2", email="user2@example.com")

        # User1: Monday 10:00-15:00 UTC (10 slots = 5 hours)
        UserAvailabilityFactory(
            user=self.user1, slots=[34.0 + (i * 0.5) for i in range(10)]
        )

        # User2: Monday 12:00-16:00 UTC (8 slots = 4 hours)
        UserAvailabilityFactory(
            user=self.user2, slots=[36.0 + (i * 0.5) for i in range(8)]
        )

    def test_calculate_team_overlap(self):
        """Test team overlap calculation."""
        # Create a captain with different availability
        captain = UserFactory(username="captain", email="captain@example.com")
        # Captain: Monday 11:00-14:00 (6 slots = 3 hours)
        UserAvailabilityFactory(
            user=captain, slots=[35.0 + (i * 0.5) for i in range(6)]
        )

        result = calculate_team_overlap(
            navigator_users=[self.user1],
            captain_user=captain,
            djangonaut_users=[self.user2],
        )

        # Navigator + djangonauts overlap (user1 + user2)
        self.assertEqual(result["navigator_meeting_hours"], 3)
        # user1 and user2 overlap is 3 hours, which is < 5 hours required
        self.assertFalse(result["is_valid"])

        # Check captain meetings
        self.assertEqual(len(result["captain_meetings"]), 1)
        # Captain 1-on-1 with user2
