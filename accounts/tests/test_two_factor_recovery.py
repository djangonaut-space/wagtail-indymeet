"""Tests for admin-initiated recovery of a locked-out account."""

import re
from datetime import timedelta

import time_machine
from django.contrib.admin.models import LogEntry
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import two_factor
from accounts.tests.test_two_factor import create_user
from accounts.tests.test_two_factor import enable_two_factor
from accounts.tests.test_two_factor import PASSWORD


def recover_url(token: str) -> str:
    return reverse("two_factor_recover", kwargs={"token": token})


class RecoveryTokenTests(TestCase):
    def setUp(self):
        self.user = create_user()
        enable_two_factor(self.user)
        self.token = two_factor.make_recovery_token(self.user)

    def test_valid_token_identifies_user(self):
        self.assertEqual(two_factor.get_user_for_recovery_token(self.token), self.user)

    def test_tampered_token_is_rejected(self):
        self.assertIsNone(two_factor.get_user_for_recovery_token(self.token + "x"))
        self.assertIsNone(two_factor.get_user_for_recovery_token("not-a-token"))

    def test_token_expires(self):
        expiry = timedelta(seconds=two_factor.RECOVERY_TOKEN_MAX_AGE)

        with time_machine.travel(timezone.now() + expiry - timedelta(minutes=1)):
            self.assertIsNotNone(two_factor.get_user_for_recovery_token(self.token))
        with time_machine.travel(timezone.now() + expiry + timedelta(minutes=1)):
            self.assertIsNone(two_factor.get_user_for_recovery_token(self.token))

    def test_token_is_void_once_two_factor_is_reset(self):
        two_factor.disable_two_factor(self.user)
        self.assertIsNone(two_factor.get_user_for_recovery_token(self.token))

        enable_two_factor(self.user)
        self.assertIsNone(two_factor.get_user_for_recovery_token(self.token))

    def test_token_is_void_for_deactivated_user(self):
        self.user.is_active = False
        self.user.save()

        self.assertIsNone(two_factor.get_user_for_recovery_token(self.token))


@override_settings(ENVIRONMENT="production")
class TwoFactorRecoverViewTests(TestCase):
    def setUp(self):
        self.user = create_user()
        enable_two_factor(self.user)
        self.link = recover_url(two_factor.make_recovery_token(self.user))
        # Where the emailed link lands once the token has moved to the session.
        self.url = recover_url("confirm")

    def test_invalid_link_redirects_to_login(self):
        for url in (recover_url("not-a-token"), self.url):
            with self.subTest(url=url):
                response = self.client.get(url, follow=True)

                self.assertRedirects(response, reverse("login"))
                self.assertContains(
                    response, "This recovery link is invalid or has expired."
                )

    def test_link_redirects_to_url_without_the_token(self):
        response = self.client.get(self.link)

        self.assertRedirects(response, self.url)

    def test_opening_the_link_changes_nothing(self):
        response = self.client.get(self.link, follow=True)

        self.assertContains(response, "Reset two-factor authentication")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertTrue(two_factor.has_two_factor(self.user))
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_wrong_password_changes_nothing(self):
        self.client.get(self.link)
        response = self.client.post(self.url, {"password": "wrong"})

        self.assertContains(response, "Incorrect password.")
        self.assertTrue(two_factor.has_two_factor(self.user))
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(len(mail.outbox), 0)

    def test_correct_password_resets_two_factor_and_starts_setup(self):
        self.client.get(self.link)
        response = self.client.post(self.url, {"password": PASSWORD}, follow=True)

        self.assertRedirects(response, reverse("two_factor_setup"))
        self.assertContains(response, "Two-factor authentication has been reset.")
        self.assertFalse(two_factor.has_two_factor(self.user))
        self.assertEqual(two_factor.remaining_recovery_codes(self.user), 0)
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("was reset", mail.outbox[0].subject)

    def test_link_works_only_once(self):
        self.client.get(self.link)
        self.client.post(self.url, {"password": PASSWORD})
        self.assertRedirects(
            self.client.post(self.url, {"password": PASSWORD}),
            reverse("login"),
            fetch_redirect_response=False,
        )
        self.client.logout()

        self.assertRedirects(self.client.get(self.link), reverse("login"))
        response = self.client.post(self.url, {"password": PASSWORD})

        self.assertRedirects(response, reverse("login"))
        self.assertNotIn(SESSION_KEY, self.client.session)


@override_settings(ENVIRONMENT="production")
class SendRecoveryEmailAdminActionTests(TestCase):
    def setUp(self):
        self.superuser = create_user(is_staff=True, is_superuser=True)
        self.locked_out_user = create_user()
        enable_two_factor(self.locked_out_user)
        self.changelist_url = reverse("admin:accounts_customuser_changelist")

    def run_action(self, *users):
        return self.client.post(
            self.changelist_url,
            {
                "action": "send_two_factor_recovery_email",
                "_selected_action": [user.pk for user in users],
            },
            follow=True,
        )

    def test_superuser_sends_working_recovery_link(self):
        self.client.force_login(self.superuser)

        response = self.run_action(self.locked_out_user)

        self.assertContains(response, "Sent a two-factor recovery email to 1 user(s).")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.locked_out_user.email])
        path = re.search(r"/accounts/two-factor/recover/\S+/", message.body).group()
        self.assertIn(path, message.alternatives[0][0])

        self.client.logout()
        response = self.client.get(path)
        self.client.post(response.url, {"password": PASSWORD})
        self.assertFalse(two_factor.has_two_factor(self.locked_out_user))

    def test_sending_is_recorded_in_admin_history(self):
        self.client.force_login(self.superuser)

        self.run_action(self.locked_out_user)

        entry = LogEntry.objects.get(object_id=str(self.locked_out_user.pk))
        self.assertEqual(entry.user, self.superuser)
        self.assertEqual(entry.change_message, "Sent two-factor recovery email.")

    def test_users_without_two_factor_are_skipped(self):
        other_user = create_user()
        self.client.force_login(self.superuser)

        response = self.run_action(self.locked_out_user, other_user)

        self.assertContains(
            response,
            f"Skipped users without two-factor authentication: {other_user.username}",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.locked_out_user.email])

    def test_action_is_not_available_to_other_staff(self):
        staff = create_user(is_staff=True)
        staff.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="accounts", content_type__model="customuser"
            )
        )
        self.client.force_login(staff)

        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "send_two_factor_recovery_email")

        self.run_action(self.locked_out_user)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(two_factor.has_two_factor(self.locked_out_user))
