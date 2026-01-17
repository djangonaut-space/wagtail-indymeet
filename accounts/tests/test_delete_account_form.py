"""Tests for account deletion form."""

from django.test import TestCase

from accounts.factories import UserFactory
from accounts.forms import DeleteAccountForm


class DeleteAccountFormTests(TestCase):
    """Tests for DeleteAccountForm."""

    def setUp(self):
        self.user = UserFactory.create(username="testuser")
        self.user.set_password("testpassword123")
        self.user.save()

    def test_valid_form_with_correct_password(self):
        form = DeleteAccountForm({"password": "testpassword123"}, user=self.user)
        self.assertTrue(form.is_valid())

    def test_invalid_form_with_incorrect_password(self):
        form = DeleteAccountForm({"password": "wrongpassword"}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)
        self.assertIn("Incorrect password", form.errors["password"][0])

    def test_requires_password(self):
        form = DeleteAccountForm({}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_empty_password_is_invalid(self):
        form = DeleteAccountForm({"password": ""}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)
