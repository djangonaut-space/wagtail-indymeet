"""Tests for account deletion background task."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from accounts.factories import UserFactory
from accounts.models import CustomUser, UserProfile
from accounts.tasks import delete_user_account
from home.factories import SessionFactory, SessionMembershipFactory
from home.models import SessionMembership, Waitlist


class DeleteUserAccountTaskTests(TestCase):
    """Tests for the delete_user_account task."""

    def setUp(self):
        self.user = UserFactory.create(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )
        self.user_id = self.user.id

        session = SessionFactory.create()
        SessionMembershipFactory.create(
            user=self.user, session=session, role=SessionMembership.DJANGONAUT
        )

        Waitlist.objects.create(user=self.user, session=session)

    @patch("accounts.tasks.email.send")
    def test_deletes_user_and_sends_confirmation_email(self, mock_send):
        self.assertTrue(CustomUser.objects.filter(pk=self.user_id).exists())

        delete_user_account.call(user_id=self.user_id)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["email_template"], "account_deleted_confirmation")
        self.assertEqual(call_kwargs["recipient_list"], ["test@example.com"])
        self.assertEqual(call_kwargs["context"]["user_name"], "Test User")

        self.assertFalse(CustomUser.objects.filter(pk=self.user_id).exists())

    @patch("accounts.tasks.email.send")
    def test_deletion_proceeds_even_if_email_fails(self, mock_send):
        mock_send.side_effect = Exception("Email service down")

        self.assertTrue(CustomUser.objects.filter(pk=self.user_id).exists())

        with self.assertRaises(Exception):
            delete_user_account.call(user_id=self.user_id)

        self.assertFalse(CustomUser.objects.filter(pk=self.user_id).exists())
