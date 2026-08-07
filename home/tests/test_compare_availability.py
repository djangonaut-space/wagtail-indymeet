"""Tests for the compare availability views."""

from datetime import datetime
from zoneinfo import ZoneInfo

import factory
from django.http import QueryDict
from django.test import Client, TestCase
from django.urls import reverse
from freezegun import freeze_time

from accounts.factories import UserAvailabilityFactory, UserFactory
from home import constants
from home.factories import (
    OrganizerFactory,
    ProjectFactory,
    SessionFactory,
    SessionMembershipFactory,
)
from home.models import SessionMembership, Team
from home.slots import Slot
from home.views.compare_availability import (
    CompareAvailabilityForm,
    build_grid_data,
    get_slot_color,
    get_user_compare_timezone,
)
from home.widgets import TomSelectMultipleWidget
from tests.timezones import (
    CENTRAL_EUROPEAN_TIMEZONE,
    DEFAULT_TIMEZONE,
    PACIFIC_AUCKLAND_TIMEZONE,
    QUARTER_HOUR_TIMEZONE,
    US_EASTERN_TIMEZONE,
)


class GetSlotColorTests(TestCase):
    """Tests for the get_slot_color function."""

    def test_no_users_returns_none(self) -> None:
        """When total_count is 0, return None."""
        self.assertIsNone(get_slot_color(0, 0))

    def test_none_available_returns_none(self) -> None:
        """When no users are available, return None."""
        self.assertIsNone(get_slot_color(0, 3))

    def test_all_available_returns_full_opacity(self) -> None:
        """When all users are available, return full opacity purple."""
        color = get_slot_color(3, 3)
        self.assertEqual(color, "rgba(92, 2, 135, 1.0)")

    def test_partial_availability_returns_proportional_opacity(self) -> None:
        """When some users are available, return proportional opacity."""
        color = get_slot_color(1, 2)
        self.assertEqual(color, "rgba(92, 2, 135, 0.35)")

        color = get_slot_color(2, 4)
        self.assertEqual(color, "rgba(92, 2, 135, 0.35)")


class BuildGridDataTests(TestCase):
    """Tests for the build_grid_data function."""

    def test_returns_48_rows(self) -> None:
        """Returns 48 rows (24 hours * 2 half-hours)."""
        rows, _ = build_grid_data([], {}, DEFAULT_TIMEZONE)
        self.assertEqual(len(rows), 48)

    def test_each_row_has_7_cells(self) -> None:
        """Each row has 7 cells (one per day)."""
        rows, _ = build_grid_data([], {}, DEFAULT_TIMEZONE)
        for row in rows:
            self.assertEqual(len(row.cells), 7)

    def test_slot_availability_mapping(self) -> None:
        """Slot availability returns list of slotAvailabilities dataclasses."""
        user1 = UserFactory.create()
        user2 = UserFactory.create()
        UserAvailabilityFactory.create(user=user1, slots=[0.0, 0.5])
        UserAvailabilityFactory.create(user=user2, slots=[0.0])

        user_slots = {
            user1.id: {Slot(DEFAULT_TIMEZONE, 0.0), Slot(DEFAULT_TIMEZONE, 0.5)},
            user2.id: {Slot(DEFAULT_TIMEZONE, 0.0)},
        }
        _, slot_availabilities = build_grid_data(
            [user1, user2], user_slots, DEFAULT_TIMEZONE
        )

        # Slot 0-0-0 (Sunday 0:00) should have both users
        self.assertIn(user1.id, slot_availabilities["0-0"])
        self.assertIn(user2.id, slot_availabilities["0-0"])

        # Slot 0-0-1 (Sunday 0:30) should only have user1
        self.assertIn(user1.id, slot_availabilities["0-0.5"])
        self.assertNotIn(user2.id, slot_availabilities["0-0.5"])

    def test_time_labels_on_hour_rows(self) -> None:
        """Time labels appear on full hour rows."""
        rows, _ = build_grid_data([], {}, DEFAULT_TIMEZONE)

        # First row (0:00) should have time label
        self.assertTrue(rows[0].show_time_label)
        self.assertEqual(rows[0].time_label, "0:00")

        # Second row (0:30) should not have time label
        self.assertFalse(rows[1].show_time_label)
        self.assertEqual(rows[1].time_label, "")

    def test_cells_have_display_time(self) -> None:
        """Each cell has a formatted display time string."""
        rows, _ = build_grid_data([], {}, DEFAULT_TIMEZONE)
        self.assertEqual(rows[0].cells[0].slot.format_local, "Sun 12:00 AM")
        self.assertEqual(rows[0].cells[1].slot.format_local, "Mon 12:00 AM")
        self.assertEqual(rows[1].cells[0].slot.format_local, "Sun 12:30 AM")

    def test_cells_have_utc_datetime(self) -> None:
        """Each cell exposes the UTC instant of its slot."""
        rows, _ = build_grid_data([], {}, DEFAULT_TIMEZONE)
        cell = rows[0].cells[0]
        self.assertEqual(cell.slot.utc, Slot("UTC", 0.0).utc)

    @freeze_time("2024-06-17")
    def test_utc_datetime_accounts_for_viewer_timezone(self) -> None:
        """utc_datetime converts back to UTC for the viewer timezone."""
        rows_timezone, _ = build_grid_data([], {}, US_EASTERN_TIMEZONE)
        # New York is UTC-4 in June, so local Sun 00:00 maps to UTC Sun 04:00.
        utc_dt = rows_timezone[0].cells[0].slot.utc
        self.assertEqual(utc_dt, Slot("UTC", 4.0).utc)
        # Display time should still show local time.
        self.assertEqual(rows_timezone[0].cells[0].slot.format_local, "Sun 12:00 AM")

    @freeze_time("2024-06-17")
    def test_grid_allows_quarter_hour_viewer_timezone_without_matching_cells(
        self,
    ) -> None:
        """Quarter-hour viewer zones are accepted despite imperfect grid fit."""
        rows_timezone, _ = build_grid_data([], {}, QUARTER_HOUR_TIMEZONE)

        # Local Sunday 00:00 in Kathmandu is the *preceding* Saturday 18:15 UTC.
        # This is allowed, but exposes the first-pass limitation: the displayed
        # grid is still built from 30-minute local cells while UTC reference
        # slots may be quarter-hour aligned.
        cell = rows_timezone[0].cells[0]
        self.assertEqual(
            cell.slot.utc,
            datetime(2024, 6, 15, 18, 15, tzinfo=ZoneInfo("UTC")),
        )
        self.assertEqual(cell.slot.format_local, "Sun 12:00 AM")

    @freeze_time("2024-06-17")
    def test_mixed_timezone_users_overlap_in_viewer_grid(self) -> None:
        """Users in different slot timezones overlap by the instant they share."""
        ny_user = UserFactory.create()
        berlin_user = UserFactory.create()
        # Mon 09:00 in New York and Mon 15:00 in Berlin are both Mon 13:00 UTC.
        user_slots = {
            ny_user.id: {Slot(US_EASTERN_TIMEZONE, 33.0)},
            berlin_user.id: {Slot(CENTRAL_EUROPEAN_TIMEZONE, 39.0)},
        }

        _, slot_availabilities = build_grid_data(
            [ny_user, berlin_user],
            user_slots,
            DEFAULT_TIMEZONE,
        )

        # Monday 13:00 UTC should contain both users.
        self.assertEqual(
            set(slot_availabilities["1-13"]),
            {ny_user.id, berlin_user.id},
        )


@freeze_time("2024-06-15")
class CompareAvailabilityTests(TestCase):
    """Tests for compare_availability."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data once for all tests in this class."""
        cls.session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 8, 30).date(),
        )

        cls.project = ProjectFactory.create(name="Django")
        cls.team = Team.objects.create(
            session=cls.session, project=cls.project, name="Team Alpha"
        )

        # Create users with availability
        cls.captain, cls.navigator, cls.djangonaut = UserFactory.create_batch(
            3,
            first_name=factory.Iterator(["Captain", "Navigator", "Django"]),
            last_name=factory.Iterator(["Marvel", "Smith", "Learner"]),
        )

        UserAvailabilityFactory.create_batch(
            3,
            user=factory.Iterator([cls.captain, cls.navigator, cls.djangonaut]),
            slots=factory.Iterator([[0.0, 0.5, 1.0], [0.0, 1.0, 2.0], [0.0, 0.5]]),
        )

        # Create memberships
        SessionMembershipFactory.create_batch(
            3,
            session=cls.session,
            team=cls.team,
            accepted=True,
            user=factory.Iterator([cls.captain, cls.navigator, cls.djangonaut]),
            role=factory.Iterator(
                [
                    constants.CAPTAIN,
                    constants.NAVIGATOR,
                    constants.DJANGONAUT,
                ]
            ),
        )

        cls.url = reverse("compare_availability")

    def setUp(self) -> None:
        """Set up per-test state."""
        self.client = Client()

    def test_anonymous_user_redirected_to_login(self) -> None:
        """Anonymous users are redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_selected_users_from_query_params(self) -> None:
        """Users can be pre-selected via query params."""
        membership = OrganizerFactory.create()

        self.client.force_login(membership.user)
        response = self.client.get(
            f"{self.url}?users={self.captain.id}&users={self.navigator.id}"
        )
        self.assertEqual(response.status_code, 200)

        selected_user_ids = response.context["selected_user_ids"]
        self.assertIn(self.captain.id, selected_user_ids)
        self.assertIn(self.navigator.id, selected_user_ids)

    def test_selected_users_multiple_params(self) -> None:
        """Users can be selected via multiple query params (form submission)."""
        membership = OrganizerFactory.create()

        self.client.force_login(membership.user)
        response = self.client.get(
            f"{self.url}?users={self.captain.id}&users={self.navigator.id}"
        )
        self.assertEqual(response.status_code, 200)

        selected_user_ids = response.context["selected_user_ids"]
        self.assertIn(self.captain.id, selected_user_ids)
        self.assertIn(self.navigator.id, selected_user_ids)

    def test_invalid_session_id_shows_form_error(self) -> None:
        """Invalid session ID shows form error."""
        self.client.force_login(self.djangonaut)
        response = self.client.get(f"{self.url}?session=99999")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertIn("session", response.context["form"].errors)

    def test_options_are_selected_in_form(self) -> None:
        """Selected users show as selected in the form."""
        membership = OrganizerFactory.create()

        self.client.force_login(membership.user)
        response = self.client.get(f"{self.url}?users={self.captain.id}")

        # Check that the selected attribute appears for the captain
        self.assertContains(response, f'value="{self.captain.id}"')
        # The captain should have 'selected' attribute
        content = response.content.decode()
        captain_option_start = content.find(f'value="{self.captain.id}"')
        captain_option_end = content.find(">", captain_option_start)
        captain_option = content[captain_option_start:captain_option_end]
        self.assertIn("selected", captain_option)

    def test_uses_requesting_users_availability_timezone(self) -> None:
        """The page initializes the grid timezone from the requesting user."""
        membership = OrganizerFactory.create()
        UserAvailabilityFactory.create(
            user=membership.user,
            slots_timezone=US_EASTERN_TIMEZONE,
        )

        self.client.force_login(membership.user)
        response = self.client.get(f"{self.url}?users={self.captain.id}")

        self.assertEqual(response.context["timezone_name"], US_EASTERN_TIMEZONE)
        self.assertContains(response, f"availabilityGrid('{US_EASTERN_TIMEZONE}')")
        self.assertContains(
            response, f'"timezone": getBrowserTimezone() || "{US_EASTERN_TIMEZONE}"'
        )


@freeze_time("2024-06-15")
class CompareAvailabilityGridTests(TestCase):
    """Tests for the compare_availability_grid view."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 8, 30).date(),
        )
        cls.project = ProjectFactory.create(name="Django")
        cls.team = Team.objects.create(
            session=cls.session, project=cls.project, name="Team Alpha"
        )

        cls.user_a, cls.user_b = UserFactory.create_batch(
            2,
            first_name=factory.Iterator(["Alice", "Bob"]),
            last_name=factory.Iterator(["Available", "Busy"]),
        )
        UserAvailabilityFactory.create(user=cls.user_a, slots=[0.0, 0.5])
        UserAvailabilityFactory.create(user=cls.user_b, slots=[0.0])
        cls.ny_user = UserFactory.create(first_name="New", last_name="York")
        cls.berlin_user = UserFactory.create(first_name="Berlin", last_name="User")
        UserAvailabilityFactory.create(
            user=cls.ny_user,
            slots=[33.0],  # Monday 9:00 America/New_York -> Monday 13:00 UTC
            slots_timezone=US_EASTERN_TIMEZONE,
        )
        UserAvailabilityFactory.create(
            user=cls.berlin_user,
            slots=[39.0],  # Monday 15:00 Europe/Berlin -> Monday 13:00 UTC
            slots_timezone=CENTRAL_EUROPEAN_TIMEZONE,
        )

        SessionMembershipFactory.create_batch(
            4,
            session=cls.session,
            team=cls.team,
            accepted=True,
            user=factory.Iterator(
                [
                    cls.user_a,
                    cls.user_b,
                    cls.ny_user,
                    cls.berlin_user,
                ]
            ),
            role=constants.DJANGONAUT,
        )
        cls.url = reverse("compare_availability_grid")

    def setUp(self) -> None:
        self.client = Client()
        self.organizer = OrganizerFactory.create()
        self.client.force_login(self.organizer.user)

    def test_grid_contains_display_time_data_attribute(self) -> None:
        """Grid cells have data-display-time attributes."""
        response = self.client.get(
            f"{self.url}?users={self.user_a.id}&users={self.user_b.id}"
            f"&timezone={DEFAULT_TIMEZONE}"
        )
        self.assertContains(response, 'data-display-time="Sun 12:00 AM"')

    def test_grid_contains_time_is_url_data_attribute(self) -> None:
        """Grid cells have data-time-is-url attributes linking to time.is."""
        response = self.client.get(
            f"{self.url}?users={self.user_a.id}&users={self.user_b.id}"
            f"&timezone={DEFAULT_TIMEZONE}"
        )
        self.assertContains(response, 'data-time-is-url="https://time.is/compare/')

    def test_grid_contains_click_handler(self) -> None:
        """Grid cells have click handlers for pinning."""
        response = self.client.get(
            f"{self.url}?users={self.user_a.id}&users={self.user_b.id}"
            f"&timezone={DEFAULT_TIMEZONE}"
        )
        self.assertContains(response, "@click=")
        self.assertContains(response, "fixedSlot")

    def test_grid_contains_time_info_section(self) -> None:
        """Grid contains the time info display section with time.is link."""
        response = self.client.get(
            f"{self.url}?users={self.user_a.id}&users={self.user_b.id}"
            f"&timezone={DEFAULT_TIMEZONE}"
        )
        self.assertContains(response, "activeDisplayTime")
        self.assertContains(response, "View on time.is")

    def test_grid_contains_server_validated_timezone_label(self) -> None:
        """Grid displays the server-validated timezone name."""
        response = self.client.get(
            f"{self.url}?users={self.user_a.id}&timezone={US_EASTERN_TIMEZONE}"
        )
        self.assertContains(response, US_EASTERN_TIMEZONE)

    def test_grid_accepts_browser_submitted_timezone_name(self) -> None:
        """The HTMX grid endpoint uses the browser-submitted IANA timezone."""
        response = self.client.get(
            f"{self.url}?users={self.user_a.id}&timezone={PACIFIC_AUCKLAND_TIMEZONE}"
        )
        self.assertContains(response, PACIFIC_AUCKLAND_TIMEZONE)
        self.assertContains(response, 'data-display-time="Sun 12:00 AM"')

    def test_mixed_timezone_users_overlap_correctly(self) -> None:
        """The grid compares per-user UTC reference slots, not raw local slots."""
        response = self.client.get(
            f"{self.url}?users={self.ny_user.id}&users={self.berlin_user.id}"
            f"&timezone={DEFAULT_TIMEZONE}"
        )
        self.assertEqual(response.status_code, 200)
        slot_availabilities = response.context["slot_availabilities"]

        self.assertEqual(
            set(slot_availabilities["1-13"]),
            {self.ny_user.id, self.berlin_user.id},
        )
        self.assertEqual(slot_availabilities["1-9"], [])
        self.assertEqual(slot_availabilities["1-15"], [])


@freeze_time("2024-06-15")
class CompareAvailabilityFormTests(TestCase):
    """Tests for CompareAvailabilityForm new logic."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.organizer_membership = OrganizerFactory.create()
        cls.organizer = cls.organizer_membership.user

        cls.session = SessionFactory.create(
            start_date=datetime(2024, 6, 1).date(),
            end_date=datetime(2024, 8, 30).date(),
        )
        project = ProjectFactory.create()
        team = Team.objects.create(
            session=cls.session, project=project, name="Team Alpha"
        )
        cls.member = UserFactory.create()
        UserAvailabilityFactory.create(user=cls.member, slots=[0.0])
        SessionMembershipFactory.create(
            session=cls.session,
            team=team,
            accepted=True,
            user=cls.member,
            role=constants.DJANGONAUT,
        )

    def _make_form(self, user, data: str | dict) -> CompareAvailabilityForm:
        if isinstance(data, str):
            data = QueryDict(data)
        return CompareAvailabilityForm(data=data, user=user)

    def test_choices_populated_from_session(self) -> None:
        """Widget choices are set from the selectable users for the given session."""
        form = self._make_form(self.organizer, f"session={self.session.pk}")
        choice_ids = {int(pk) for pk, _ in form.fields["users"].choices}
        self.assertIn(self.member.id, choice_ids)

    def test_invalid_session_id_falls_back_to_no_session(self) -> None:
        """A non-existent session PK does not raise; choices are computed without session."""
        form = self._make_form(self.organizer, "session=999999")
        self.assertIsInstance(form.fields["users"].choices, list)

    def test_clean_users_returns_set_of_ints(self) -> None:
        """clean_users converts the MultipleChoiceField strings to a set of ints."""
        form = self._make_form(
            self.organizer,
            f"session={self.session.pk}&users={self.member.id}",
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["users"], {self.member.id})

    def test_timezone_defaults_to_utc(self) -> None:
        """Timezone defaults to UTC when the user has no availability timezone."""
        form = self._make_form(self.organizer, "")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["timezone"], DEFAULT_TIMEZONE)
        self.assertEqual(form.get_timezone_name(), DEFAULT_TIMEZONE)

    def test_timezone_defaults_to_user_availability_timezone(self) -> None:
        """Timezone defaults to the requesting user's availability timezone."""
        UserAvailabilityFactory.create(
            user=self.organizer,
            slots_timezone=US_EASTERN_TIMEZONE,
        )
        form = self._make_form(self.organizer, "")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["timezone"], US_EASTERN_TIMEZONE)
        self.assertEqual(form.get_timezone_name(), US_EASTERN_TIMEZONE)

    def test_get_user_compare_timezone_falls_back_to_utc(self) -> None:
        """Users without availability compare in UTC by default."""
        user = UserFactory.create()
        self.assertEqual(get_user_compare_timezone(user), DEFAULT_TIMEZONE)

    def test_timezone_accepts_valid_iana_name(self) -> None:
        """Timezone accepts valid submitted IANA names."""
        form = self._make_form(self.organizer, f"timezone={US_EASTERN_TIMEZONE}")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["timezone"], US_EASTERN_TIMEZONE)

    def test_submitted_timezone_overrides_user_availability_timezone(self) -> None:
        """An explicit submitted timezone overrides the user's default timezone."""
        UserAvailabilityFactory.create(
            user=self.organizer,
            slots_timezone=US_EASTERN_TIMEZONE,
        )
        form = self._make_form(self.organizer, f"timezone={PACIFIC_AUCKLAND_TIMEZONE}")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["timezone"], PACIFIC_AUCKLAND_TIMEZONE)

    def test_timezone_rejects_invalid_name(self) -> None:
        """Timezone rejects non-IANA names."""
        form = self._make_form(self.organizer, "timezone=Not/AZone")
        self.assertFalse(form.is_valid())
        self.assertIn("timezone", form.errors)

    def test_user_id_not_in_choices_is_rejected(self) -> None:
        """Submitting a user ID outside the selectable set fails validation."""
        outsider = UserFactory.create()
        form = self._make_form(
            self.organizer,
            f"session={self.session.pk}&users={outsider.id}",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("users", form.errors)
