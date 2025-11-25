"""Tests for account deletion views."""

from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from accounts.factories import UserFactory
from home.factories import SessionFactory, SessionMembershipFactory
from home.models import SessionMembership


class DeleteAccountConfirmationViewTests(TestCase):
    """Tests for DeleteAccountView GET requests (confirmation page)."""

    def setUp(self):
        self.client = Client()
        self.user = UserFactory.create(username="testuser")
        self.url = reverse("delete_account")

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_displays_confirmation_page(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete Account")
        self.assertContains(response, "This action cannot be undone")
        self.assertContains(response, "password")

    def test_shows_related_data_counts(self):
        session = SessionFactory.create()
        SessionMembershipFactory.create(
            user=self.user, session=session, role=SessionMembership.DJANGONAUT
        )

        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertContains(response, "session memberships")
        self.assertContains(response, "(1)")


class DeleteAccountViewTests(TestCase):
    """Tests for DeleteAccountView POST requests (deletion processing)."""

    def setUp(self):
        self.client = Client()
        self.user = UserFactory.create(username="testuser", email="test@example.com")
        self.user.set_password("testpassword123")
        self.user.save()
        self.url = reverse("delete_account")

    def test_requires_login(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_blocks_staff_users(self):
        staff_user = UserFactory.create(username="staff", is_staff=True)
        self.client.force_login(staff_user)

        response = self.client.get(self.url, follow=True)

        self.assertRedirects(response, reverse("profile"))
        self.assertContains(response, "Staff accounts cannot be deleted")

    @patch("accounts.views.delete_user_account")
    def test_successful_deletion_enqueues_task_and_logs_out(self, mock_task):
        user_id = self.user.id

        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            {"password": "testpassword123"},
            follow=True,
        )

        mock_task.enqueue.assert_called_once_with(user_id=user_id)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "account deletion has been initiated")
