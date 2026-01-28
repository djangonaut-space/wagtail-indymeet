"""Tests for the compare availability views."""

from datetime import datetime

import factory
from django.test import Client, TestCase
from django.urls import reverse
from freezegun import freeze_time

from accounts.factories import UserAvailabilityFactory, UserFactory
from home.factories import (
    OrganizerFactory,
    ProjectFactory,
    SessionFactory,
    SessionMembershipFactory,
)
from home.models import SessionMembership, Team
from home.views.compare_availability import (
    build_grid_data,
    get_slot_color,
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
        self.assertEqual(color, "rgba(92, 2, 135, 0.5)")

        color = get_slot_color(2, 4)
        self.assertEqual(color, "rgba(92, 2, 135, 0.5)")


class BuildGridDataTests(TestCase):
    """Tests for the build_grid_data function."""

    def test_returns_48_rows(self) -> None:
        """Returns 48 rows (24 hours * 2 half-hours)."""
        rows, _ = build_grid_data([], {}, 0)
        self.assertEqual(len(rows), 48)

    def test_each_row_has_7_cells(self) -> None:
        """Each row has 7 cells (one per day)."""
        rows, _ = build_grid_data([], {}, 0)
        for row in rows:
            self.assertEqual(len(row.cells), 7)

    def test_slot_availability_mapping(self) -> None:
        """Slot availability returns list of slotAvailabilities dataclasses."""
        user1 = UserFactory.create()
        user2 = UserFactory.create()
        UserAvailabilityFactory.create(user=user1, slots=[0.0, 0.5])
        UserAvailabilityFactory.create(user=user2, slots=[0.0])

        user_slots = {user1.id: {0.0, 0.5}, user2.id: {0.0}}
        _, slot_availabilities = build_grid_data([user1, user2], user_slots, 0)

        # Slot 0-0-0 (Sunday 0:00) should have both users
        self.assertIn(user1.id, slot_availabilities["0-0-0"])
        self.assertIn(user2.id, slot_availabilities["0-0-0"])

        # Slot 0-0-1 (Sunday 0:30) should only have user1
        self.assertIn(user1.id, slot_availabilities["0-0-1"])
        self.assertNotIn(user2.id, slot_availabilities["0-0-1"])

    def test_time_labels_on_hour_rows(self) -> None:
        """Time labels appear on full hour rows."""
        rows, _ = build_grid_data([], {}, 0)

        # First row (0:00) should have time label
        self.assertTrue(rows[0].show_time_label)
        self.assertEqual(rows[0].time_label, "0:00")

        # Second row (0:30) should not have time label
        self.assertFalse(rows[1].show_time_label)
        self.assertEqual(rows[1].time_label, "")


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
                    SessionMembership.CAPTAIN,
                    SessionMembership.NAVIGATOR,
                    SessionMembership.DJANGONAUT,
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

    def test_user_with_permission_can_access(self) -> None:
        """Users with compare_org_availability permission can access."""
        membership = OrganizerFactory.create()

        self.client.force_login(membership.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_user_without_permission_or_session_shows_empty_list(self) -> None:
        """Users without permission or session context see empty selectable users."""
        user = UserFactory.create()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selectable_users"], [])

    def test_session_organizer_can_see_all_participants(self) -> None:
        """Session organizers can see all session participants."""
        membership = OrganizerFactory.create(session=self.session)
        UserAvailabilityFactory.create(user=membership.user, slots=[0.0])

        self.client.force_login(membership.user)
        response = self.client.get(f"{self.url}?session={self.session.id}")
        self.assertEqual(response.status_code, 200)

        # Check all users with availability are in selectable_users
        selectable_users = response.context["selectable_users"]
        user_ids = [u.id for u in selectable_users]
        self.assertIn(self.captain.id, user_ids)
        self.assertIn(self.navigator.id, user_ids)
        self.assertIn(self.djangonaut.id, user_ids)

    def test_team_member_can_only_see_team_members(self) -> None:
        """Team members can only see their team members."""
        self.client.force_login(self.djangonaut)
        response = self.client.get(f"{self.url}?session={self.session.id}")
        self.assertEqual(response.status_code, 200)

        selectable_users = response.context["selectable_users"]
        user_ids = [u.id for u in selectable_users]
        self.assertIn(self.captain.id, user_ids)
        self.assertIn(self.navigator.id, user_ids)
        self.assertIn(self.djangonaut.id, user_ids)

    def test_team_member_cannot_see_other_team(self) -> None:
        """Team members cannot see members from other teams."""
        other_team = Team.objects.create(
            session=self.session, project=self.project, name="Team Beta"
        )
        other_user = UserFactory.create(first_name="Other", last_name="User")
        UserAvailabilityFactory.create(user=other_user, slots=[0.0])
        SessionMembershipFactory.create(
            user=other_user,
            session=self.session,
            team=other_team,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )

        self.client.force_login(self.djangonaut)
        response = self.client.get(f"{self.url}?session={self.session.id}")

        selectable_users = response.context["selectable_users"]
        user_ids = [u.id for u in selectable_users]
        self.assertNotIn(other_user.id, user_ids)

    def test_selected_users_from_query_params(self) -> None:
        """Users can be pre-selected via query params."""
        membership = OrganizerFactory.create()

        self.client.force_login(membership.user)
        response = self.client.get(
            f"{self.url}?users={self.captain.id},{self.navigator.id}"
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

    def test_non_member_of_session_shows_empty_list(self) -> None:
        """User not a member of the session sees empty selectable users."""
        other_user = UserFactory.create()
        self.client.force_login(other_user)
        response = self.client.get(f"{self.url}?session={self.session.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selectable_users"], [])

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
