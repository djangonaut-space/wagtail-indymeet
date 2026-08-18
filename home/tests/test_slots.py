"""Tests for the timezone-aware Slot value object."""

import dataclasses
import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from freezegun import freeze_time

from accounts.factories import UserAvailabilityFactory
from home.slots import Slot
from tests.timezones import (
    CENTRAL_EUROPEAN_TIMEZONE,
    QUARTER_HOUR_TIMEZONE,
    US_EASTERN_TIMEZONE,
)


@freeze_time("2024-06-17")
class SlotTestCase(TestCase):
    """Test Slot conversions, formatting, and equality."""

    def test_accepts_timezone_name_or_zoneinfo(self) -> None:
        """A plain IANA name is normalized so slots_timezone can be passed directly."""
        from_name = Slot(US_EASTERN_TIMEZONE, 33.0)
        from_zoneinfo = Slot(ZoneInfo(US_EASTERN_TIMEZONE), 33.0)
        self.assertEqual(from_name.timezone, ZoneInfo(US_EASTERN_TIMEZONE))
        self.assertEqual(from_name, from_zoneinfo)

    def test_local_datetime(self) -> None:
        """local anchors the slot to this week in its own timezone."""
        slot = Slot(US_EASTERN_TIMEZONE, 33.0)
        self.assertEqual(
            slot.local,
            datetime.datetime(2024, 6, 17, 9, 0, tzinfo=ZoneInfo(US_EASTERN_TIMEZONE)),
        )

    def test_utc_datetime(self) -> None:
        """Monday 09:00 in New York is Monday 13:00 UTC in June."""
        slot = Slot(US_EASTERN_TIMEZONE, 33.0)
        self.assertEqual(
            slot.utc,
            datetime.datetime(2024, 6, 17, 13, 0, tzinfo=ZoneInfo("UTC")),
        )

    def test_slot_local_and_slot_utc(self) -> None:
        """slot_local keeps the stored value; slot_utc shifts by the offset."""
        slot = Slot(US_EASTERN_TIMEZONE, 33.0)
        self.assertEqual(slot.slot_local, 33.0)
        self.assertEqual(slot.slot_utc, 37.0)

    def test_format_local_and_format_utc(self) -> None:
        """Formatting renders each representation as a readable weekday time."""
        slot = Slot(US_EASTERN_TIMEZONE, 33.0)
        self.assertEqual(slot.format_local, "Mon 9:00 AM")
        self.assertEqual(slot.format_utc, "Mon 1:00 PM")

    def test_half_hour_slot_formats_with_minutes(self) -> None:
        """Half-hour slots keep their :30 minutes through conversion."""
        slot = Slot("UTC", 38.5)
        self.assertEqual(slot.format_local, "Mon 2:30 PM")
        self.assertEqual(slot.slot_utc, 38.5)

    def test_as_tz(self) -> None:
        """as_tz re-expresses the same instant in a third timezone."""
        slot = Slot(US_EASTERN_TIMEZONE, 33.0)
        self.assertEqual(
            slot.as_tz(ZoneInfo(CENTRAL_EUROPEAN_TIMEZONE)),
            datetime.datetime(
                2024, 6, 17, 15, 0, tzinfo=ZoneInfo(CENTRAL_EUROPEAN_TIMEZONE)
            ),
        )

    def test_slot_as_tz(self) -> None:
        """slot_as_tz returns the viewer's wall-clock weekly slot."""
        slot = Slot(US_EASTERN_TIMEZONE, 33.0)
        self.assertEqual(slot.slot_as_tz(ZoneInfo(CENTRAL_EUROPEAN_TIMEZONE)), 39.0)

    def test_format_as_tz(self) -> None:
        """format_as_tz renders the slot for an arbitrary viewer timezone."""
        slot = Slot(US_EASTERN_TIMEZONE, 33.0)
        self.assertEqual(
            slot.format_as_tz(ZoneInfo(CENTRAL_EUROPEAN_TIMEZONE)), "Mon 3:00 PM"
        )

    def test_slot_as_tz_preserves_half_hour_precision(self) -> None:
        """Quarter-hour zones would be truncated away by an int return type."""
        slot = Slot("UTC", 33.0)
        self.assertEqual(slot.slot_as_tz(ZoneInfo(QUARTER_HOUR_TIMEZONE)), 38.75)

    def test_quarter_hour_timezone_slots_are_allowed(self) -> None:
        """Quarter-hour zones can produce non-30-minute UTC slots."""
        # Kathmandu is UTC+05:45, so Monday 9:00 local maps to Sunday 27.25 UTC
        # in weekly slot coordinates. This is intentionally allowed for now,
        # even though overlap and grid consumers still assume 30-minute cells.
        slot = Slot(QUARTER_HOUR_TIMEZONE, 33.0)
        self.assertEqual(slot.slot_utc, 27.25)
        self.assertEqual(slot.slot_as_tz(QUARTER_HOUR_TIMEZONE), 33.0)

    def test_local_to_utc_round_trips(self) -> None:
        """A slot converted to UTC and back recovers its local value."""
        utc_slot = Slot(US_EASTERN_TIMEZONE, 33.0).slot_utc
        self.assertEqual(utc_slot, 37.0)
        self.assertEqual(Slot("UTC", utc_slot).slot_as_tz(US_EASTERN_TIMEZONE), 33.0)

    def test_format_local_boundary_values(self) -> None:
        """The first and last slots of the week format correctly."""
        self.assertEqual(Slot("UTC", 0.0).format_local, "Sun 12:00 AM")
        self.assertEqual(Slot("UTC", 167.5).format_local, "Sat 11:30 PM")

    def test_utc_slot_matches_slot_as_tz_utc(self) -> None:
        """slot_utc is the UTC case of the general slot_as_tz."""
        slot = Slot(US_EASTERN_TIMEZONE, 33.0)
        self.assertEqual(slot.slot_utc, slot.slot_as_tz(ZoneInfo("UTC")))

    def test_equal_across_timezones_for_same_instant(self) -> None:
        """Different timezones naming the same instant compare and hash equal."""
        eastern = Slot(US_EASTERN_TIMEZONE, 33.0)
        berlin = Slot(CENTRAL_EUROPEAN_TIMEZONE, 39.0)
        self.assertEqual(eastern, berlin)
        self.assertEqual(hash(eastern), hash(berlin))

    def test_different_instants_are_not_equal(self) -> None:
        """The same wall-clock value in different zones is a different instant."""
        self.assertNotEqual(
            Slot(US_EASTERN_TIMEZONE, 33.0), Slot(CENTRAL_EUROPEAN_TIMEZONE, 33.0)
        )

    def test_set_intersection_across_timezones(self) -> None:
        """Overlap via set intersection works for users in different timezones."""
        eastern = {Slot(US_EASTERN_TIMEZONE, 33.0), Slot(US_EASTERN_TIMEZONE, 34.0)}
        berlin = {
            Slot(CENTRAL_EUROPEAN_TIMEZONE, 39.0),
            Slot(CENTRAL_EUROPEAN_TIMEZONE, 50.0),
        }
        self.assertEqual(eastern & berlin, {Slot("UTC", 37.0)})

    def test_sorting_orders_by_instant(self) -> None:
        """Slots sort chronologically regardless of source timezone."""
        slots = [Slot(US_EASTERN_TIMEZONE, 34.0), Slot(CENTRAL_EUROPEAN_TIMEZONE, 39.0)]
        self.assertEqual([slot.slot_utc for slot in sorted(slots)], [37.0, 38.0])

    def test_frozen(self) -> None:
        """Slots are immutable so cached conversions cannot go stale."""
        slot = Slot("UTC", 33.0)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            slot.value = 1.0

    def test_in_tz_keeps_instant_but_moves_wall_clock(self) -> None:
        """in_tz re-expresses a slot without changing which instant it is."""
        berlin = Slot(US_EASTERN_TIMEZONE, 33.0).in_tz(CENTRAL_EUROPEAN_TIMEZONE)
        self.assertEqual(berlin.value, 39.0)
        self.assertEqual(berlin.format_local, "Mon 3:00 PM")
        self.assertEqual(berlin, Slot(US_EASTERN_TIMEZONE, 33.0))

    def test_add_wraps_around_the_week(self) -> None:
        """Adding past Saturday midnight wraps to the start of the week."""
        self.assertEqual((Slot("UTC", 33.0) + 0.5).value, 33.5)
        self.assertEqual((Slot("UTC", 167.5) + 0.5).value, 0.0)

    def test_is_adjacent_to(self) -> None:
        """Adjacency means the next 30-minute slot, by instant."""
        slot = Slot("UTC", 33.0)
        self.assertTrue(slot.is_adjacent_to(Slot("UTC", 33.5)))
        self.assertFalse(slot.is_adjacent_to(Slot("UTC", 34.0)))
        # Adjacency holds across timezones because it compares instants.
        self.assertTrue(slot.is_adjacent_to(Slot(CENTRAL_EUROPEAN_TIMEZONE, 35.5)))

    def test_day_index_and_name(self) -> None:
        """Day accessors read in the slot's own timezone."""
        slot = Slot(US_EASTERN_TIMEZONE, 33.0)
        self.assertEqual(slot.day_index, 1)
        self.assertEqual(slot.day_name, "Mon")
        self.assertEqual(slot.hour_in_day, 9.0)

    def test_format_time_only_drops_weekday(self) -> None:
        """format_time_only is the display string without the day name."""
        self.assertEqual(Slot(US_EASTERN_TIMEZONE, 33.0).format_time_only, "9:00 AM")

    def test_key_identifies_wall_clock_position(self) -> None:
        """Keys name a grid cell, so equal instants in other zones differ."""
        self.assertEqual(Slot("UTC", 0.0).key, "0-0")
        self.assertEqual(Slot("UTC", 0.5).key, "0-0.5")
        self.assertEqual(Slot("UTC", 37.0).key, "1-13")
        self.assertNotEqual(
            Slot(US_EASTERN_TIMEZONE, 33.0).key,
            Slot(CENTRAL_EUROPEAN_TIMEZONE, 39.0).key,
        )


class SlotReferenceWeekTestCase(TestCase):
    """Test which calendar week slots are anchored to."""

    def test_anchors_to_current_week_sunday(self) -> None:
        """Slot 0.0 anchors to the Sunday of the frozen date's week."""
        with freeze_time("2024-06-19"):
            self.assertEqual(Slot("UTC", 0.0).utc.date(), datetime.date(2024, 6, 16))
        with freeze_time("2024-06-16"):
            self.assertEqual(Slot("UTC", 0.0).utc.date(), datetime.date(2024, 6, 16))

    def test_anchor_follows_the_calendar_across_midnight(self) -> None:
        """The memoized week start must not pin slots to a stale week."""
        with freeze_time("2024-06-22 23:59"):  # Saturday
            self.assertEqual(Slot("UTC", 0.0).utc.date(), datetime.date(2024, 6, 16))
        with freeze_time("2024-06-23 00:01"):  # Sunday, a new week
            self.assertEqual(Slot("UTC", 0.0).utc.date(), datetime.date(2024, 6, 23))


class SlotDaylightSavingTestCase(TestCase):
    """Test Slot behavior across DST transition weeks."""

    @freeze_time("2024-03-10")
    def test_uses_daylight_offset_after_spring_transition(self) -> None:
        """Sunday March 10 2024 is the US spring-forward date."""
        slot = Slot(US_EASTERN_TIMEZONE, 33.0)
        self.assertEqual(slot.slot_utc, 37.0)
        self.assertEqual(slot.format_utc, "Mon 1:00 PM")
        self.assertEqual(Slot("UTC", 37.0).slot_as_tz(US_EASTERN_TIMEZONE), 33.0)

    @freeze_time("2024-11-03")
    def test_uses_standard_offset_after_fall_transition(self) -> None:
        """Sunday November 3 2024 is the US fall-back date."""
        # Monday 9:00 in New York is Monday 14:00 UTC after DST ends.
        self.assertEqual(Slot(US_EASTERN_TIMEZONE, 33.0).slot_utc, 38.0)
        self.assertEqual(Slot("UTC", 38.0).slot_as_tz(US_EASTERN_TIMEZONE), 33.0)

    @freeze_time("2024-11-03")
    def test_fold_defaults_to_earlier_occurrence(self) -> None:
        """Ambiguous fall-back times inherit zoneinfo's fold=0 default."""
        # Sunday 1:30 occurs twice in New York. The default fold=0 occurrence is
        # still daylight time (UTC-4), so it maps to Sunday 05:30 UTC.
        self.assertEqual(Slot(US_EASTERN_TIMEZONE, 1.5).slot_utc, 5.5)
        self.assertEqual(Slot("UTC", 5.5).slot_as_tz(US_EASTERN_TIMEZONE), 1.5)

    @freeze_time("2024-03-10")
    def test_gap_defaults_to_pre_transition_offset_without_blocking(self) -> None:
        """Nonexistent spring-forward times inherit zoneinfo defaults."""
        # Sunday 2:30 does not exist in New York on the spring-forward day. The
        # first-pass policy does not reject it; zoneinfo applies the default
        # pre-transition offset, mapping it to Sunday 07:30 UTC.
        self.assertEqual(Slot(US_EASTERN_TIMEZONE, 2.5).slot_utc, 7.5)
        self.assertEqual(Slot("UTC", 7.5).slot_as_tz(US_EASTERN_TIMEZONE), 3.5)


@freeze_time("2024-06-17")
class UserAvailabilityGetSlotsTestCase(TestCase):
    """Test UserAvailability.get_slots()."""

    def test_accepts_utc_offset_label(self) -> None:
        """Fixed UTC±HH:MM offsets are stored without DST rules."""
        slot = Slot("UTC-05:00", 33.0)
        self.assertEqual(str(slot.timezone), "UTC-05:00")
        self.assertEqual(slot.slot_utc, 38.0)

    def test_returns_slots_tagged_with_row_timezone(self) -> None:
        """Each slot carries the availability row's timezone."""
        availability = UserAvailabilityFactory(
            slots=[33.0, 34.0], slots_timezone=US_EASTERN_TIMEZONE
        )
        slots = availability.get_slots()
        self.assertEqual(len(slots), 2)
        self.assertEqual(
            [slot.timezone for slot in slots],
            [ZoneInfo(US_EASTERN_TIMEZONE)] * 2,
        )
        self.assertEqual([slot.slot_utc for slot in slots], [37.0, 38.0])

    def test_empty_availability(self) -> None:
        """No stored slots yields no Slot objects."""
        self.assertEqual(UserAvailabilityFactory(slots=[]).get_slots(), [])

    def test_coerces_integer_slots(self) -> None:
        """Slots stored as JSON integers still behave as floats."""
        availability = UserAvailabilityFactory(slots=[33], slots_timezone="UTC")
        self.assertEqual(availability.get_slots()[0].slot_local, 33.0)
