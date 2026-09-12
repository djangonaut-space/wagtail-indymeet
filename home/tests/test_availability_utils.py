"""Tests for availability calculation utilities."""

from django.test import TestCase
import time_machine

from accounts.factories import UserAvailabilityFactory, UserFactory
from tests.timezones import (
    CENTRAL_EUROPEAN_TIMEZONE,
    US_EASTERN_TIMEZONE,
)
from home.slots import Slot
from home.availability import (
    AvailabilityWindow,
    calculate_overlap,
    calculate_team_overlap,
    count_one_hour_blocks,
    format_slots_as_ranges,
    get_user_slots,
)


def utc_slots(*values: float) -> list[Slot]:
    """Build UTC slots for the given weekly slot values."""
    return [Slot("UTC", value) for value in values]


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
        self.assertEqual(count_one_hour_blocks(utc_slots(10.0, 10.5)), 1)

        # Four consecutive slots = 2 hour blocks
        self.assertEqual(count_one_hour_blocks(utc_slots(10.0, 10.5, 11.0, 11.5)), 2)

        # Non-consecutive slots
        self.assertEqual(count_one_hour_blocks(utc_slots(10.0, 10.5, 12.0, 12.5)), 2)

        # Single slot
        self.assertEqual(count_one_hour_blocks(utc_slots(10.0)), 0)

        # Empty slots
        self.assertEqual(count_one_hour_blocks([]), 0)

    @time_machine.travel("2024-06-17", tick=False)
    def test_get_user_slots_preserves_utc_default_users(self):
        """UTC-default availability remains directly comparable."""
        self.assertEqual(
            [slot.slot_utc for slot in get_user_slots(self.user1)],
            self.avail1.slots,
        )

    @time_machine.travel("2024-06-17", tick=False)
    def test_get_user_slots_converts_mixed_timezone_users(self):
        """Local wall-clock slots in user timezones derive matching UTC slots."""
        ny_user = UserFactory(username="ny_user", email="ny@example.com")
        berlin_user = UserFactory(username="berlin_user", email="berlin@example.com")
        UserAvailabilityFactory(
            user=ny_user,
            slots=[33.0],  # Monday 9:00 America/New_York -> Monday 13:00 UTC
            slots_timezone=US_EASTERN_TIMEZONE,
        )
        UserAvailabilityFactory(
            user=berlin_user,
            slots=[39.0],  # Monday 15:00 Europe/Berlin -> Monday 13:00 UTC
            slots_timezone=CENTRAL_EUROPEAN_TIMEZONE,
        )

        self.assertEqual([slot.slot_utc for slot in get_user_slots(ny_user)], [37.0])
        self.assertEqual(
            [slot.slot_utc for slot in get_user_slots(berlin_user)], [37.0]
        )
        # The two users' slots are the same instant, so they compare equal.
        self.assertEqual(get_user_slots(ny_user), get_user_slots(berlin_user))

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

    def test_calculate_overlap_uses_user_timezones(self):
        """Mixed-timezone users overlap by derived UTC slots."""
        ny_user = UserFactory(username="ny_overlap", email="ny-overlap@example.com")
        berlin_user = UserFactory(
            username="berlin_overlap", email="berlin-overlap@example.com"
        )
        UserAvailabilityFactory(
            user=ny_user,
            slots=[33.0, 33.5],
            slots_timezone=US_EASTERN_TIMEZONE,
        )
        UserAvailabilityFactory(
            user=berlin_user,
            slots=[39.0, 39.5],
            slots_timezone=CENTRAL_EUROPEAN_TIMEZONE,
        )

        with time_machine.travel("2024-06-17", tick=False):
            slots, hours = calculate_overlap([ny_user, berlin_user])

        self.assertEqual([slot.slot_utc for slot in slots], [37.0, 37.5])
        self.assertEqual(hours, 1)

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

    def test_format_slots_as_ranges(self):
        """Test formatting slots as time ranges."""
        # Consecutive slots
        ranges = format_slots_as_ranges(utc_slots(10.0, 10.5, 11.0, 11.5))
        self.assertEqual(len(ranges), 1)
        self.assertIn("Sun", ranges[0])

        # Non-consecutive slots
        ranges = format_slots_as_ranges(utc_slots(10.0, 10.5, 12.0, 12.5))
        self.assertEqual(len(ranges), 2)

        # Empty slots
        ranges = format_slots_as_ranges([])
        self.assertEqual(ranges, [])

        # UTC slots displayed in a named timezone.
        with time_machine.travel("2024-06-17", tick=False):
            ranges = format_slots_as_ranges(utc_slots(37.0, 37.5), US_EASTERN_TIMEZONE)
        self.assertEqual(ranges, ["Mon 9:00 AM - 10:00 AM"])


class AvailabilityWindowTestCase(TestCase):
    """Tests for AvailabilityWindow dataclass."""

    def test_admin_unavailable_url_uses_user_ids(self):
        """Test that admin_unavailable_url uses user.id, not str(user)."""
        user1 = UserFactory(username="user1", email="user1@example.com")
        user2 = UserFactory(username="user2", email="user2@example.com")

        window = AvailabilityWindow(
            slot_range=(Slot("UTC", 10.0), Slot("UTC", 10.5)),
            formatted_time="Sun 10:00 AM - 11:00 AM",
            available_users=[],
            unavailable_users=[user1, user2],
        )

        url = window.admin_unavailable_url
        expected_ids = f"{user1.id},{user2.id}"
        self.assertIn(f"?user_id__in={expected_ids}", url)
        self.assertIn("home/sessionmembership/", url)

    def test_admin_unavailable_url_returns_none_when_no_unavailable_users(self):
        """Test that admin_unavailable_url returns None with no unavailable users."""
        window = AvailabilityWindow(
            slot_range=(Slot("UTC", 10.0), Slot("UTC", 10.5)),
            formatted_time="Sun 10:00 AM - 11:00 AM",
            available_users=[],
            unavailable_users=[],
        )

        self.assertIsNone(window.admin_unavailable_url)
