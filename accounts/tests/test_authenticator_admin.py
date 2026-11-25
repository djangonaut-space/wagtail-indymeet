"""Tests for resetting a locked-out user's two-factor authentication."""

from allauth.mfa.models import Authenticator
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.tests.two_factor_helpers import create_user
from accounts.tests.two_factor_helpers import enable_two_factor
from accounts.tests.two_factor_helpers import submit_password
from accounts.two_factor import has_two_factor

CHANGELIST_URL = reverse("admin:mfa_authenticator_changelist")


class AuthenticatorAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = create_user("admin", is_staff=True, is_superuser=True)
        cls.locked_out = create_user("lockedout")
        cls.secret = enable_two_factor(cls.locked_out)
        cls.authenticator = Authenticator.objects.get(
            user=cls.locked_out, type=Authenticator.Type.TOTP
        )

    def setUp(self):
        self.client.force_login(self.superuser)

    def delete_url(self) -> str:
        return reverse("admin:mfa_authenticator_delete", args=[self.authenticator.pk])

    def test_superuser_can_find_a_users_authenticator(self):
        response = self.client.get(CHANGELIST_URL, {"q": "lockedout"})

        self.assertContains(response, "TOTP Authenticator")

    def test_secrets_are_not_shown(self):
        response = self.client.get(
            reverse("admin:mfa_authenticator_change", args=[self.authenticator.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.secret)

    def test_authenticators_cannot_be_added_or_edited(self):
        add_response = self.client.get(reverse("admin:mfa_authenticator_add"))
        change_response = self.client.post(
            reverse("admin:mfa_authenticator_change", args=[self.authenticator.pk]),
            {"type": "totp"},
        )

        self.assertEqual(add_response.status_code, 403)
        self.assertEqual(change_response.status_code, 403)

    def test_deleting_resets_two_factor_so_a_password_is_enough(self):
        response = self.client.post(self.delete_url(), {"post": "yes"})

        self.assertRedirects(response, reverse("admin:index"))
        self.assertFalse(Authenticator.objects.filter(user=self.locked_out).exists())
        self.assertFalse(has_two_factor(self.locked_out))
        self.client.logout()
        self.assertRedirects(
            submit_password(self.client, self.locked_out), reverse("profile")
        )

    def test_deleting_is_recorded_in_the_admin_log(self):
        self.client.post(self.delete_url(), {"post": "yes"})

        entry = LogEntry.objects.get()
        self.assertEqual(entry.user, self.superuser)
        self.assertTrue(entry.is_deletion())

    def test_bulk_delete_also_removes_recovery_codes(self):
        self.client.post(
            CHANGELIST_URL,
            {
                "action": "delete_selected",
                "_selected_action": [self.authenticator.pk],
                "post": "yes",
            },
        )

        self.assertFalse(Authenticator.objects.filter(user=self.locked_out).exists())

    def test_other_users_authenticators_are_untouched(self):
        other = create_user("other")
        enable_two_factor(other)

        self.client.post(self.delete_url(), {"post": "yes"})

        self.assertTrue(has_two_factor(other))

    def test_staff_cannot_see_or_delete_authenticators_even_with_permissions(self):
        staff = create_user("staff", is_staff=True)
        staff.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="mfa")
        )
        self.client.force_login(staff)

        self.assertEqual(self.client.get(CHANGELIST_URL).status_code, 403)
        self.assertEqual(
            self.client.post(self.delete_url(), {"post": "yes"}).status_code, 403
        )
        self.assertNotContains(
            self.client.get(reverse("admin:index")), "Authenticators"
        )
        self.assertTrue(has_two_factor(self.locked_out))
