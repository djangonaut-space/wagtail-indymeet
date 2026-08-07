"""Tests for user availability functionality."""

import json

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from accounts.forms import UserAvailabilityForm
from accounts.models import UserAvailability
from home.slots import Slot
from tests.timezones import (
    CENTRAL_EUROPEAN_TIMEZONE,
    DEFAULT_TIMEZONE,
    US_EASTERN_TIMEZONE,
)

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def user_with_availability(user):
    """Create a test user with availability data."""
    availability = UserAvailability.objects.create(
        user=user,
        slots=[
            24.0,  # Monday 00:00 local (1*24 + 0)
            36.0,  # Monday 12:00 local (1*24 + 12)
            66.0,  # Tuesday 18:00 local (2*24 + 18)
        ],
        slots_timezone=US_EASTERN_TIMEZONE,
    )
    return user, availability


class TestUserAvailabilityModel:
    """Test the UserAvailability model."""

    def test_create_availability(self, user):
        """Test creating a UserAvailability object."""
        availability = UserAvailability.objects.create(user=user)
        assert availability.user == user
        assert availability.slots == []
        assert availability.slots_timezone == DEFAULT_TIMEZONE

    def test_add_slot(self, user):
        """Test adding time slots."""
        availability = UserAvailability.objects.create(user=user)
        availability.add_slot(1, 14.5)  # Monday 14:30 local
        availability.save()

        assert len(availability.slots) > 0

    def test_remove_slot(self, user):
        """Test removing time slots."""
        availability = UserAvailability.objects.create(
            user=user,
            slots=[36.0, 48.0],  # Monday 12:00, Tuesday 00:00
        )
        availability.remove_slot(1, 12.0)  # Should remove 36.0
        availability.save()

        assert 36.0 not in availability.slots

    def test_clear_slots(self, user):
        """Test clearing all slots."""
        availability = UserAvailability.objects.create(
            user=user,
            slots=[24.0, 48.0, 72.0],  # Monday, Tuesday, Wednesday at 00:00
        )
        availability.clear_slots()
        availability.save()

        assert availability.slots == []

    def test_get_slots_for_day(self, user):
        """Test getting slots for a specific day."""
        availability = UserAvailability.objects.create(
            user=user,
            slots=[
                24.0,  # Monday 00:00
                36.0,  # Monday 12:00
                48.0,  # Tuesday 00:00
            ],
        )
        monday_slots = availability.get_slots_for_day(1)

        assert len(monday_slots) == 2
        assert 0.0 in monday_slots
        assert 12.0 in monday_slots

    def test_string_representation(self, user):
        """Test the string representation."""
        availability = UserAvailability.objects.create(user=user)
        assert str(availability) == f"{user.username}'s availability"


class TestAvailabilityView:
    """Test the availability view."""

    def test_availability_view_requires_login(self, client):
        """Test that the availability view requires login."""
        url = reverse("availability")
        response = client.get(url)

        assert response.status_code == 302  # Redirect to login
        assert "/accounts/login" in response.url

    def test_availability_view_authenticated(self, client, user):
        """Test that authenticated users can access the view."""
        client.force_login(user)
        url = reverse("availability")
        response = client.get(url)

        content = response.content.decode()
        assert response.status_code == 200
        assert "availability-grid" in content
        assert "id_slots_timezone" in content
        assert response.context["default_availability_timezone"] == DEFAULT_TIMEZONE

    def test_availability_view_creates_object(self, client, user):
        """Test that the view creates a UserAvailability object if none exists."""
        client.force_login(user)
        url = reverse("availability")
        client.get(url)

        assert UserAvailability.objects.filter(user=user).exists()

    def test_availability_view_loads_existing_data(
        self, client, user_with_availability
    ):
        """Test that existing availability data is loaded."""
        user, availability = user_with_availability
        client.force_login(user)
        url = reverse("availability")
        response = client.get(url)

        content = response.content.decode()
        assert str(availability.slots) in content
        assert f'value="{US_EASTERN_TIMEZONE}" selected' in content

    def test_availability_update(self, client, user):
        """Test updating availability via POST."""
        client.force_login(user)
        url = reverse("availability")

        # Create some test local slots
        # Mon 09:00, Mon 12:00, Tue 00:00
        test_slots = [33.0, 36.0, 48.0]
        response = client.post(
            url,
            {
                "slots": json.dumps(test_slots),
                "slots_timezone": US_EASTERN_TIMEZONE,
            },
        )

        assert response.status_code == 302  # Redirect after success

        # Check that the data was saved as local slots in the selected timezone
        availability = UserAvailability.objects.get(user=user)
        assert availability.slots == test_slots
        assert availability.slots_timezone == US_EASTERN_TIMEZONE

    def test_availability_clear_all(self, client, user_with_availability):
        """Test clearing all availability."""
        user, availability = user_with_availability
        client.force_login(user)
        url = reverse("availability")

        response = client.post(
            url,
            {
                "slots": json.dumps([]),
                "slots_timezone": availability.slots_timezone,
            },
        )

        assert response.status_code == 302

        availability.refresh_from_db()
        assert availability.slots == []
        assert availability.slots_timezone == US_EASTERN_TIMEZONE


class TestAvailabilityForm(TestCase):
    """Test the UserAvailabilityForm."""

    @classmethod
    def setUpTestData(cls):
        """Create a shared test user for all tests in this class."""
        cls.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def test_form_valid_with_slots(self):
        """Test form validation with valid slot data."""
        availability = UserAvailability.objects.create(user=self.user)
        form = UserAvailabilityForm(
            data={
                "slots": [24.0, 48.0, 72.0],  # Mon, Tue, Wed at 00:00
                "slots_timezone": DEFAULT_TIMEZONE,
            },
            instance=availability,
        )

        assert form.is_valid()

    def test_form_valid_with_empty_slots(self):
        """Test form validation with empty slots."""
        availability = UserAvailability.objects.create(user=self.user)
        form = UserAvailabilityForm(
            data={"slots": [], "slots_timezone": DEFAULT_TIMEZONE},
            instance=availability,
        )

        assert form.is_valid()

    def test_form_saves_slots(self):
        """Test that the form saves slot data correctly."""
        availability = UserAvailability.objects.create(user=self.user)
        test_slots = [
            24.0,
            36.0,
            48.0,
            60.0,
        ]  # Mon 00:00, Mon 12:00, Tue 00:00, Tue 12:00
        form = UserAvailabilityForm(
            data={"slots": test_slots, "slots_timezone": CENTRAL_EUROPEAN_TIMEZONE},
            instance=availability,
        )

        assert form.is_valid()
        saved_availability = form.save()

        assert saved_availability.slots == test_slots
        assert saved_availability.slots_timezone == CENTRAL_EUROPEAN_TIMEZONE

    def test_form_timezone_choices_include_iana_zones(self):
        """Test that the timezone selector offers IANA timezone names."""
        availability = UserAvailability.objects.create(user=self.user)
        form = UserAvailabilityForm(instance=availability)
        timezone_values = {
            value for value, label in form.fields["slots_timezone"].choices
        }

        assert DEFAULT_TIMEZONE in timezone_values
        assert US_EASTERN_TIMEZONE in timezone_values
        assert CENTRAL_EUROPEAN_TIMEZONE in timezone_values

    def test_form_rejects_invalid_timezone(self):
        """Test that availability cannot be saved with an unknown timezone."""
        availability = UserAvailability.objects.create(user=self.user)
        form = UserAvailabilityForm(
            data={"slots": [24.0], "slots_timezone": "Not/AZone"},
            instance=availability,
        )

        assert not form.is_valid()
        assert "slots_timezone" in form.errors

    def test_form_requires_timezone(self):
        """Test that omitting the timezone fails validation instead of silently
        falling back to the previously saved value."""
        availability = UserAvailability.objects.create(
            user=self.user,
            slots=[33.0],
            slots_timezone=US_EASTERN_TIMEZONE,
        )
        form = UserAvailabilityForm(data={"slots": [33.0, 33.5]}, instance=availability)

        assert not form.is_valid()
        assert "slots_timezone" in form.errors

    def test_converts_utc_slots_to_profile_timezone(self):
        """UserAvailabilityForm.__init__ should convert default-UTC slots
        to the user's UserProfile.timezone (e.g. detected by the browser)
        for display, so the grid and timezone field show the same
        timezone the JS auto-detect would have picked."""
        self.user.profile.timezone = US_EASTERN_TIMEZONE
        self.user.profile.save()
        availability = UserAvailability.objects.create(
            user=self.user,
            slots=[33.0, 36.0],  # Mon 09:00, Mon 12:00 UTC
            slots_timezone=DEFAULT_TIMEZONE,
        )

        form = UserAvailabilityForm(instance=availability)

        expected_slots = [
            Slot("UTC", 33.0).slot_as_tz(US_EASTERN_TIMEZONE),
            Slot("UTC", 36.0).slot_as_tz(US_EASTERN_TIMEZONE),
        ]
        assert form.instance.slots == expected_slots
        assert form.instance.slots_timezone == US_EASTERN_TIMEZONE
        # form.initial is derived from the instance, so the rendered
        # select reflects the conversion too.
        assert form.initial["slots_timezone"] == US_EASTERN_TIMEZONE

    def test_skips_conversion_when_timezone_customized(self):
        """Once a user has explicitly saved a non-UTC timezone, it must
        never be silently overridden by their profile timezone."""
        self.user.profile.timezone = US_EASTERN_TIMEZONE
        self.user.profile.save()
        availability = UserAvailability.objects.create(
            user=self.user,
            slots=[33.0],
            slots_timezone=CENTRAL_EUROPEAN_TIMEZONE,
        )

        form = UserAvailabilityForm(instance=availability)

        assert form.instance.slots == [33.0]
        assert form.instance.slots_timezone == CENTRAL_EUROPEAN_TIMEZONE


@pytest.mark.django_db
class TestProfilePageAvailabilityLink:
    """Test that the profile page shows availability information."""

    def test_profile_shows_availability_not_set(self, client, user):
        """Test that profile shows 'not set' when no availability exists."""
        client.force_login(user)
        url = reverse("profile")
        response = client.get(url)

        content = response.content.decode()
        assert "Not set" in content or "not set" in content.lower()

    def test_profile_shows_availability_set(self, client, user_with_availability):
        """Test that profile shows availability when it's set."""
        user, availability = user_with_availability
        client.force_login(user)
        url = reverse("profile")
        response = client.get(url)

        content = response.content.decode()
        # Should show that availability is set and number of slots
        assert "Set" in content or "set" in content.lower()

    def test_profile_has_availability_link(self, client, user):
        """Test that profile has a link to the availability page."""
        client.force_login(user)
        url = reverse("profile")
        response = client.get(url)

        content = response.content.decode()
        availability_url = reverse("availability")
        assert availability_url in content


class TestUserAvailabilityAdmin:
    """Test the UserAvailability admin interface."""

    @pytest.fixture
    def admin_user(self, db):
        """Create an admin user."""
        return User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )

    def test_availability_admin_list_display(
        self, client, admin_user, user_with_availability
    ):
        """Test that the admin list view displays correctly."""
        user, availability = user_with_availability
        client.force_login(admin_user)
        url = reverse("admin:accounts_useravailability_changelist")
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert user.username in content
        # Should show the slot count
        assert "3" in content  # user_with_availability has 3 slots

    def test_availability_admin_search(
        self, client, admin_user, user_with_availability
    ):
        """Test searching for users in the admin."""
        user, availability = user_with_availability
        client.force_login(admin_user)
        url = reverse("admin:accounts_useravailability_changelist")
        response = client.get(url, {"q": user.username})

        assert response.status_code == 200
        content = response.content.decode()
        assert user.username in content

    def test_availability_admin_change_view(
        self, client, admin_user, user_with_availability
    ):
        """Test the admin change view."""
        user, availability = user_with_availability
        client.force_login(admin_user)
        url = reverse("admin:accounts_useravailability_change", args=[availability.pk])
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        # Should show readonly updated_at field
        assert "updated_at" in content.lower()

    def test_slot_count_display(self, user_with_availability):
        """Test the slot_count admin display method."""
        from accounts.admin import UserAvailabilityAdmin

        user, availability = user_with_availability
        admin_instance = UserAvailabilityAdmin(UserAvailability, None)
        slot_count = admin_instance.slot_count(availability)

        assert slot_count == 3


class TestUserAvailabilityFormEdgeCases:
    """Test edge cases for UserAvailabilityForm."""

    def test_form_with_invalid_json(self, user):
        """Test form validation with mixed data types."""
        availability = UserAvailability.objects.create(user=user)
        # JSONField should handle conversion, but let's test with proper list
        form = UserAvailabilityForm(
            data={
                "slots": [24.0, "invalid", 48.0],
                "slots_timezone": DEFAULT_TIMEZONE,
            },
            instance=availability,
        )

        # Form should still be valid as JSONField accepts lists
        # The validation happens at the application level
        assert form.is_valid()

    def test_form_with_none_slots(self, user):
        """Test form with None value for slots."""
        availability = UserAvailability.objects.create(user=user)
        form = UserAvailabilityForm(
            data={"slots_timezone": DEFAULT_TIMEZONE},  # No slots provided
            instance=availability,
        )

        # Should be valid - slots is not required
        assert form.is_valid()

    def test_form_clears_slots_on_empty_submit(self, user):
        """Test that submitting empty list clears slots."""
        availability = UserAvailability.objects.create(
            user=user,
            slots=[24.0, 48.0, 72.0],  # Mon, Tue, Wed at 00:00
        )
        # JSONField converts empty list to empty list (valid value)
        form = UserAvailabilityForm(
            data={"slots": json.dumps([]), "slots_timezone": DEFAULT_TIMEZONE},
            instance=availability,
        )

        assert form.is_valid()
        saved = form.save()
        # When explicitly set to empty list, it should clear the slots
        assert saved.slots == []


class TestUpdateAvailabilityViewEdgeCases:
    """Test edge cases for UpdateAvailabilityView."""

    def test_multiple_updates_change_timestamp(self, client, user):
        """Test that multiple updates change the updated_at timestamp."""
        import time

        client.force_login(user)
        url = reverse("availability")

        # First update
        response = client.post(
            url,
            {"slots": json.dumps([24.0, 48.0]), "slots_timezone": DEFAULT_TIMEZONE},
        )
        assert response.status_code == 302

        availability = UserAvailability.objects.get(user=user)
        first_timestamp = availability.updated_at

        # Wait a moment
        time.sleep(0.1)

        # Second update
        response = client.post(
            url,
            {
                "slots": json.dumps([24.0, 48.0, 72.0]),
                "slots_timezone": DEFAULT_TIMEZONE,
            },
        )
        assert response.status_code == 302

        availability.refresh_from_db()
        second_timestamp = availability.updated_at

        # Timestamp should have changed
        assert second_timestamp > first_timestamp

    def test_get_object_creates_availability_once(self, client, user):
        """Test that get_object doesn't create duplicate availability records."""
        client.force_login(user)
        url = reverse("availability")

        # Multiple GET requests
        client.get(url)
        client.get(url)
        client.get(url)

        # Should only have one availability record
        count = UserAvailability.objects.filter(user=user).count()
        assert count == 1

    def test_success_message_displayed(self, client, user):
        """Test that success message is displayed after update."""
        client.force_login(user)
        url = reverse("availability")

        response = client.post(
            url,
            {"slots": json.dumps([24.0]), "slots_timezone": DEFAULT_TIMEZONE},
            follow=True,
        )

        # Check for success message
        messages = list(response.context["messages"])
        assert len(messages) == 1
        assert "successfully" in str(messages[0]).lower()

    def test_redirects_to_profile(self, client, user):
        """Test that the view redirects to profile after successful update."""
        client.force_login(user)
        url = reverse("availability")

        response = client.post(
            url,
            {"slots": json.dumps([24.0]), "slots_timezone": DEFAULT_TIMEZONE},
        )

        assert response.status_code == 302
        assert response.url == reverse("profile")


class TestUserAvailabilityModelEdgeCases:
    """Test edge cases for UserAvailability model methods."""

    def test_add_duplicate_slot(self, user):
        """Test that adding a duplicate slot doesn't create duplicates."""
        availability = UserAvailability.objects.create(user=user)
        availability.add_slot(1, 14.5)
        availability.add_slot(1, 14.5)  # Add same slot again
        availability.save()

        # Should only have one slot
        assert len(availability.slots) == 1

    def test_add_slot_maintains_sort_order(self, user):
        """Test that add_slot maintains sorted order."""
        availability = UserAvailability.objects.create(user=user)
        availability.add_slot(3, 10.0)
        availability.add_slot(1, 14.5)
        availability.add_slot(2, 8.0)
        availability.save()

        # Slots should be sorted
        assert availability.slots == sorted(availability.slots)

    def test_remove_nonexistent_slot(self, user):
        """Test removing a slot that doesn't exist."""
        availability = UserAvailability.objects.create(
            user=user,
            slots=[24.0, 48.0],  # Monday and Tuesday at midnight
        )
        availability.remove_slot(5, 10.0)  # Slot that doesn't exist (Fri 10:00 = 130.0)
        availability.save()

        # Should still have original slots
        assert len(availability.slots) == 2

    def test_get_slots_for_day_empty(self, user):
        """Test getting slots for a day with no availability."""
        availability = UserAvailability.objects.create(
            user=user,
            slots=[24.0, 48.0],  # Monday and Tuesday at midnight
        )
        sunday_slots = availability.get_slots_for_day(0)

        assert sunday_slots == []

    def test_get_slots_for_day_multiple_times(self, user):
        """Test getting multiple time slots for the same day."""
        availability = UserAvailability.objects.create(
            user=user,
            slots=[
                24.0,  # Monday 00:00 (1*24 + 0)
                30.0,  # Monday 06:00 (1*24 + 6)
                36.0,  # Monday 12:00 (1*24 + 12)
                42.0,  # Monday 18:00 (1*24 + 18)
            ],
        )
        monday_slots = availability.get_slots_for_day(1)

        assert len(monday_slots) == 4
        assert 0.0 in monday_slots
        assert 6.0 in monday_slots
        assert 12.0 in monday_slots
        assert 18.0 in monday_slots

    def test_slot_calculation_boundary_values(self, user):
        """Test slot calculations with boundary values."""
        availability = UserAvailability.objects.create(user=user)

        # Test Sunday at 00:00 (minimum = 0*24 + 0 = 0.0)
        availability.add_slot(0, 0.0)
        assert 0.0 in availability.slots

        # Test Saturday at 23:30 (maximum = 6*24 + 23.5 = 167.5)
        availability.add_slot(6, 23.5)
        assert 167.5 in availability.slots

    def test_one_to_one_relationship(self, user):
        """Test that a user can only have one availability record."""

        UserAvailability.objects.create(user=user)

        # Attempting to create another should raise IntegrityError
        with pytest.raises(IntegrityError):
            UserAvailability.objects.create(user=user)
