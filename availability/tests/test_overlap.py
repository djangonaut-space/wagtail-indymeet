"""Tests for availability calculation utilities."""

from django.test import TestCase

from accounts.factories import UserFactory
from availability.factories import UserAvailabilityFactory
from availability.overlap import (
    AvailabilityWindow,
    calculate_overlap,
    calculate_user_overlap,
    count_one_hour_blocks,
    find_best_one_hour_windows,
)


class AvailabilityUtilsTestCase(TestCase):
    """Test availability calculation utilities."""

    def setUp(self):
        """Create test users with availability."""
        self.user1 = UserFactory(username="user1", email="user1@example.com")
        self.user2 = UserFactory(username="user2", email="user2@example.com")
        self.user3 = UserFactory(username="user3", email="user3@example.com")

        # User1: Monday 10:00-15:00 UTC (10 slots = 5 hours)
        # Slots: 34.0, 34.5, 35.0, 35.5, 36.0, 36.5, 37.0, 37.5, 38.0, 38.5
        self.avail1 = UserAvailabilityFactory(
            user=self.user1, slots=[34.0 + (i * 0.5) for i in range(10)]
        )

        # User2: Monday 12:00-16:00 UTC (8 slots = 4 hours)
        # Slots: 36.0, 36.5, 37.0, 37.5, 38.0, 38.5, 39.0, 39.5
        self.avail2 = UserAvailabilityFactory(
            user=self.user2, slots=[36.0 + (i * 0.5) for i in range(8)]
        )

        # User3: No availability
        # (no UserAvailability object created)

    def test_count_one_hour_blocks(self):
        """Test counting 1-hour blocks from slots."""
        # Two consecutive slots = 1 hour block
        slots = [10.0, 10.5]
        self.assertEqual(count_one_hour_blocks(slots), 1)

        # Four consecutive slots = 2 hour blocks
        slots = [10.0, 10.5, 11.0, 11.5]
        self.assertEqual(count_one_hour_blocks(slots), 2)

        # Non-consecutive slots
        slots = [10.0, 10.5, 12.0, 12.5]
        self.assertEqual(count_one_hour_blocks(slots), 2)

        # Single slot
        slots = [10.0]
        self.assertEqual(count_one_hour_blocks(slots), 0)

        # Empty slots
        self.assertEqual(count_one_hour_blocks([]), 0)

        # Gap before a consecutive pair
        slots = [10.0, 11.0, 11.5]
        self.assertEqual(count_one_hour_blocks(slots), 1)

    def test_calculate_overlap(self):
        """Test overlap calculation for groups and pairs."""
        # User1 and User2 overlap on Monday 12:00-15:00 (6 slots = 3 hours)
        # Expected overlap: 36.0, 36.5, 37.0, 37.5, 38.0, 38.5
        slots, hours = calculate_overlap([self.user1, self.user2])
        self.assertEqual(hours, 3)
        self.assertEqual(len(slots), 6)

        # Single user (returns their full availability)
        slots, hours = calculate_overlap([self.user1])
        self.assertEqual(hours, 5)

        # User with no availability
        slots, hours = calculate_overlap([self.user3])
        self.assertEqual(hours, 0)
        self.assertEqual(slots, [])

        # Mixed: user with and without availability
        slots, hours = calculate_overlap([self.user1, self.user3])
        self.assertEqual(hours, 0)  # No overlap because user3 has no availability

        # No users
        self.assertEqual(calculate_overlap([]), ([], 0))

    def test_calculate_user_overlap(self):
        """Test the two-user convenience wrapper around calculate_overlap."""
        slots = calculate_user_overlap(self.user1, self.user2)
        self.assertEqual(len(slots), 6)

    def test_find_best_one_hour_windows(self):
        """Test ranking one-hour windows by how many users are available."""
        windows = find_best_one_hour_windows([self.user1, self.user2], top_n=2)
        self.assertEqual(len(windows), 2)
        self.assertTrue(all(window.total_available == 2 for window in windows))
        self.assertIn("Mon", windows[0].formatted_time)

    def test_availability_window_properties(self):
        """Test the AvailabilityWindow dataclass' derived properties."""
        window = AvailabilityWindow(
            slot_range=(34.0, 34.5),  # Monday 10:00-11:00
            formatted_time="Mon 10:00 AM - 11:00 AM",
            available_users=[self.user1, self.user2],
            unavailable_users=[self.user3],
            role_counts={"Captain": 1, "Navigator": 0},
        )
        self.assertEqual(window.total_available, 2)
        self.assertEqual(window.role_summary, "Captain: 1")
        self.assertEqual(window.unavailable_member_ids, [self.user3.id])
        self.assertEqual(window.start_datetime.weekday(), 0)  # Monday
