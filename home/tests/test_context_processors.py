"""Tests for context processors."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.factories import UserAvailabilityFactory, UserFactory
from accounts.models import UserAvailability
from home.factories import SessionFactory, SurveyFactory


class AlertAboutStatusViewIntegrationTestCase(TestCase):
    """Test that alert_about_status context is available in views."""

    def setUp(self):
        """Set up test data."""
        self.user = UserFactory()

    def test_user_needs_to_set_availability(self):
        """Test that user without availability gets flag in session list view."""
        today = timezone.now().date()
        survey = SurveyFactory()
        SessionFactory(
            application_survey=survey,
            application_start_date=today - timedelta(days=5),
            application_end_date=today + timedelta(days=5),
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("session_list"))

        self.assertEqual(response.status_code, 200)
        # User should be flagged to set availability
        self.assertTrue(response.context.get("user_needs_to_set_availability"))

    def test_user_needs_to_update_availability(self):
        """Test that user with stale availability gets update flag in session list view."""
        today = timezone.now().date()
        survey = SurveyFactory()
        SessionFactory(
            application_survey=survey,
            application_start_date=today - timedelta(days=5),
            application_end_date=today + timedelta(days=5),
        )

        # Create stale availability
        availability = UserAvailabilityFactory(user=self.user, slots=[24.0, 24.5])
        # Set updated_at to more than 30 days ago using update() to bypass auto_now
        old_time = timezone.now() - timedelta(days=31)
        UserAvailability.objects.filter(id=availability.id).update(updated_at=old_time)

        # Refresh the user to clear any cached relationships
        self.user.refresh_from_db()
        self.client.force_login(self.user)
        response = self.client.get(reverse("session_list"))

        self.assertEqual(response.status_code, 200)
        # User should be flagged to update
        self.assertTrue(response.context.get("user_needs_to_update_availability"))
        self.assertIsNone(response.context.get("user_needs_to_set_availability"))

    def test_no_active_application_session(self):
        """Test that no flags are set when there's no active application session."""
        today = timezone.now().date()
        SessionFactory(
            application_start_date=today + timedelta(days=10),
            application_end_date=today + timedelta(days=20),
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("session_list"))

        self.assertEqual(response.status_code, 200)
        # No flags should be set
        self.assertIsNone(response.context.get("user_needs_to_set_availability"))
        self.assertIsNone(response.context.get("user_needs_to_update_availability"))
