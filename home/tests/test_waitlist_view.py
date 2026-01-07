"""Tests for waitlist integration with team formation view."""

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from accounts.factories import UserFactory
from home.factories import SessionFactory, SurveyFactory
from home.models import SessionMembership, UserSurveyResponse, Waitlist


class WaitlistViewTestCase(TestCase):
    """Test waitlist functionality in the team formation view."""

    def setUp(self):
        """Create test data and authenticated admin user."""
        self.session = SessionFactory()
        self.survey = SurveyFactory(session=self.session)
        self.session.application_survey = self.survey
        self.session.save()

        # Create admin user with permissions
        self.admin_user = UserFactory(is_staff=True, is_superuser=True)

        # Add form_team permission
        permission = Permission.objects.get(codename="form_team")
        self.admin_user.user_permissions.add(permission)

        # Create applicant users
        self.applicant1 = UserFactory(username="applicant1")
        self.applicant2 = UserFactory(username="applicant2")
        self.applicant3 = UserFactory(username="applicant3")

        # Create survey responses
        UserSurveyResponse.objects.create(user=self.applicant1, survey=self.survey)
        UserSurveyResponse.objects.create(user=self.applicant2, survey=self.survey)
        UserSurveyResponse.objects.create(user=self.applicant3, survey=self.survey)

        # Create client and login
        self.client = Client()
        self.client.force_login(self.admin_user)

        # URLs
        self.team_formation_url = reverse(
            "admin:session_form_teams", args=[self.session.id]
        )
        self.waitlist_url = reverse(
            "admin:session_add_to_waitlist", args=[self.session.id]
        )

    def test_waitlist_form_displayed_on_page(self):
        """Test that the waitlist form is rendered in the team formation view."""
        response = self.client.get(self.team_formation_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add to Waitlist")
        self.assertContains(response, "waitlist-form")

    def test_waitlisted_user_displayed_in_team_column(self):
        """Test that waitlisted users are shown as 'Waitlisted' in the Team column."""
        # Add applicant1 to waitlist
        Waitlist.objects.create(user=self.applicant1, session=self.session)

        response = self.client.get(self.team_formation_url)

        self.assertEqual(response.status_code, 200)
        # Check that "Waitlisted" appears in the response for this user
        self.assertContains(response, "Waitlisted")

    def test_successful_waitlist_addition(self):
        """Test successfully adding users to waitlist via POST."""
        data = {
            "bulk_waitlist-user_ids": f"{self.applicant1.id},{self.applicant2.id}",
        }

        response = self.client.post(self.waitlist_url, data, follow=True)

        # Should redirect with success message
        self.assertEqual(response.status_code, 200)

        # Check for success message
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("Successfully added 2 user(s) to the waitlist", str(messages[0]))

        # Verify database entries
        self.assertTrue(
            Waitlist.objects.filter(user=self.applicant1, session=self.session).exists()
        )
        self.assertTrue(
            Waitlist.objects.filter(user=self.applicant2, session=self.session).exists()
        )

    def test_requires_authentication(self):
        """Test that the view requires authentication."""
        self.client.logout()
        response = self.client.get(self.waitlist_url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_requires_permission(self):
        """Test that the view requires form_team permission."""
        # Create user without permission
        regular_user = UserFactory(is_staff=True)
        self.client.force_login(regular_user)

        response = self.client.post(self.waitlist_url, {})

        # Should redirect (no permission) or be forbidden
        # Django admin redirects to login when permission is denied
        self.assertIn(response.status_code, [302, 403])
