from django.test import TestCase

from accounts.factories import UserFactory
from accounts.views import CustomPasswordResetForm


class CustomPasswordResetFormGetUsersTests(TestCase):
    """Tests for CustomPasswordResetForm.get_users.

    The key difference from Django's base PasswordResetForm is that this
    implementation includes users with unusable passwords, enabling password
    resets for social auth users who have not yet set a local password.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create(email="test@example.com", is_active=True)
        cls.user.set_password("password123")
        cls.user.save()

    def _get_users(self, email: str) -> list:
        return list(CustomPasswordResetForm().get_users(email))

    def test_returns_active_user_with_matching_email(self):
        users = self._get_users("test@example.com")
        self.assertEqual(users, [self.user])

    def test_excludes_inactive_user(self):
        inactive_user = UserFactory.create(
            email="inactive@example.com", is_active=False
        )
        users = self._get_users(inactive_user.email)
        self.assertEqual(users, [])

    def test_includes_user_with_unusable_password(self):
        """Users with unusable passwords are included, unlike the base class."""
        unusable_user = UserFactory.create(email="unusable@example.com", is_active=True)
        unusable_user.set_unusable_password()
        unusable_user.save()
        users = self._get_users(unusable_user.email)
        self.assertEqual(users, [unusable_user])

    def test_case_insensitive_email_match(self):
        users = self._get_users("TEST@EXAMPLE.COM")
        self.assertEqual(users, [self.user])

    def test_no_match_returns_empty(self):
        users = self._get_users("nonexistent@example.com")
        self.assertEqual(users, [])
