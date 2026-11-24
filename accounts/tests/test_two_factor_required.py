"""Tests for the deadline after which two-factor authentication is mandatory."""

from datetime import timedelta

from django.contrib.auth import SESSION_KEY
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import two_factor
from accounts.tests.two_factor_helpers import create_user
from accounts.tests.two_factor_helpers import enable_two_factor
from accounts.tests.two_factor_helpers import reauthenticate

REMINDER = "Two-factor authentication will be required for all accounts from"


def days_from_today(days: int):
    return timezone.localdate() + timedelta(days=days)


class NoDeadlineTests(TestCase):
    def test_two_factor_is_optional_and_unadvertised(self):
        self.client.force_login(create_user())

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, REMINDER)
        self.assertFalse(two_factor.is_required())


@override_settings(TWO_FACTOR_REQUIRED_FROM=days_from_today(30))
class BeforeDeadlineTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.client.force_login(self.user)

    def test_user_without_two_factor_sees_reminder_but_is_not_blocked(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, REMINDER)
        self.assertContains(response, days_from_today(30).strftime("%Y"))
        self.assertContains(response, reverse("mfa_activate_totp"))

    def test_user_with_two_factor_sees_no_reminder(self):
        enable_two_factor(self.user)

        response = self.client.get(reverse("profile"))

        self.assertNotContains(response, REMINDER)

    def test_anonymous_user_sees_no_reminder(self):
        self.client.logout()

        response = self.client.get(reverse("login"))

        self.assertNotContains(response, REMINDER)

    def test_two_factor_can_still_be_turned_off(self):
        enable_two_factor(self.user)
        reauthenticate(self.client)

        response = self.client.post(reverse("mfa_deactivate_totp"))

        self.assertRedirects(response, reverse("mfa_index"))
        self.assertFalse(two_factor.has_two_factor(self.user))


@override_settings(TWO_FACTOR_REQUIRED_FROM=days_from_today(-1))
class AfterDeadlineTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.client.force_login(self.user)
        self.setup_url = reverse("mfa_activate_totp")

    @override_settings(TWO_FACTOR_REQUIRED_FROM=days_from_today(0))
    def test_requirement_starts_on_the_deadline_day(self):
        self.assertTrue(two_factor.is_required())
        self.assertRedirects(
            self.client.get(reverse("profile")),
            self.setup_url,
            fetch_redirect_response=False,
        )

    def test_user_without_two_factor_is_redirected_to_setup(self):
        for url in (
            reverse("profile"),
            reverse("availability"),
            reverse("mfa_view_recovery_codes"),
            reverse("socialaccount_connections"),
            reverse("admin:index"),
            reverse("wagtailadmin_home"),
        ):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), self.setup_url, fetch_redirect_response=False
                )

    def test_post_requests_are_redirected_too(self):
        response = self.client.post(reverse("update_user"), {"first_name": "New"})

        self.assertRedirects(response, self.setup_url, fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.first_name, "New")

    def test_redirect_explains_why(self):
        response = self.client.get(reverse("profile"), follow=True)

        self.assertContains(
            response, "Two-factor authentication is now required for all accounts."
        )
        self.assertNotContains(response, REMINDER)

    def test_setup_can_be_completed(self):
        """The password check and the setup page itself must stay reachable."""
        response = self.client.get(self.setup_url)
        self.assertRedirects(
            response,
            f"{reverse('account_reauthenticate')}?next={self.setup_url}",
        )

        reauthenticate(self.client)

        self.assertEqual(self.client.get(self.setup_url).status_code, 200)

    def test_unconfirmed_user_can_reach_what_they_need_to_confirm_their_email(self):
        self.user.profile.email_confirmed = False
        self.user.profile.save()
        reauthenticate(self.client)

        response = self.client.get(self.setup_url, follow=True)

        self.assertRedirects(response, reverse("mfa_index"))
        self.assertContains(response, "until you have verified your email address")
        response = self.client.post(reverse("resend_email_confirmation"))
        self.assertRedirects(
            response, reverse("profile"), fetch_redirect_response=False
        )

    def test_user_can_log_out(self):
        self.client.post(reverse("logout"))

        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_user_can_cancel_a_login_from_the_code_step(self):
        self.client.post(reverse("account_logout"))

        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_background_timezone_update_is_not_redirected(self):
        response = self.client.post(
            reverse("update_timezone"), {"timezone": "Europe/London"}
        )

        self.assertNotEqual(response.status_code, 302)

    def test_user_with_two_factor_is_not_redirected(self):
        enable_two_factor(self.user)

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)

    def test_anonymous_users_are_not_redirected(self):
        self.client.logout()

        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)

    def test_removing_authenticator_leads_straight_back_to_setup(self):
        """Replacing an authenticator app: remove it, then set up the new one."""
        enable_two_factor(self.user)
        reauthenticate(self.client)

        self.client.post(reverse("mfa_deactivate_totp"))

        self.assertFalse(two_factor.has_two_factor(self.user))
        self.assertRedirects(
            self.client.get(reverse("profile")),
            self.setup_url,
            fetch_redirect_response=False,
        )
