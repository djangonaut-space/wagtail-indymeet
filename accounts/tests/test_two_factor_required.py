"""Tests for the deadline after which two-factor authentication is mandatory."""

from datetime import timedelta

from django.contrib.auth import SESSION_KEY
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import two_factor
from accounts.tests.test_two_factor import create_user
from accounts.tests.test_two_factor import enable_two_factor
from accounts.tests.test_two_factor import PASSWORD

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
        self.assertContains(response, reverse("two_factor_setup"))

    def test_user_with_two_factor_sees_no_reminder(self):
        enable_two_factor(self.user)

        response = self.client.get(reverse("profile"))

        self.assertNotContains(response, REMINDER)

    def test_anonymous_user_sees_no_reminder(self):
        self.client.logout()

        response = self.client.get(reverse("login"))

        self.assertNotContains(response, REMINDER)

    def test_overview_mentions_deadline_and_still_offers_turning_off(self):
        enable_two_factor(self.user)

        response = self.client.get(reverse("two_factor"))

        self.assertContains(response, "will be required for all accounts from")
        self.assertContains(response, "Turn off two-factor authentication")

    def test_two_factor_can_still_be_turned_off(self):
        enable_two_factor(self.user)

        response = self.client.post(
            reverse("two_factor_disable"), {"password": PASSWORD}
        )

        self.assertRedirects(response, reverse("two_factor"))
        self.assertFalse(two_factor.has_two_factor(self.user))


@override_settings(TWO_FACTOR_REQUIRED_FROM=days_from_today(-1))
class AfterDeadlineTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.client.force_login(self.user)
        self.setup_url = reverse("two_factor_setup")

    @override_settings(TWO_FACTOR_REQUIRED_FROM=days_from_today(0))
    def test_requirement_starts_on_the_deadline_day(self):
        self.assertTrue(two_factor.is_required())
        self.assertRedirects(self.client.get(reverse("profile")), self.setup_url)

    def test_user_without_two_factor_is_redirected_to_setup(self):
        for url in (
            reverse("profile"),
            reverse("availability"),
            reverse("two_factor"),
            reverse("admin:index"),
            reverse("wagtailadmin_home"),
        ):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), self.setup_url, fetch_redirect_response=False
                )

    def test_post_requests_are_redirected_too(self):
        response = self.client.post(reverse("update_user"), {"first_name": "New"})

        self.assertRedirects(response, self.setup_url)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.first_name, "New")

    def test_setup_page_is_reachable_and_explains_why(self):
        response = self.client.get(reverse("profile"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Two-factor authentication is now required for all accounts."
        )
        self.assertNotContains(response, REMINDER)

    def test_user_can_log_out(self):
        self.client.post(reverse("logout"))

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

    def test_pending_setup_does_not_satisfy_the_requirement(self):
        two_factor.get_or_create_pending_device(self.user)

        self.assertRedirects(self.client.get(reverse("profile")), self.setup_url)

    def test_anonymous_users_are_not_redirected(self):
        self.client.logout()

        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)

    def test_overview_offers_replacing_instead_of_turning_off(self):
        enable_two_factor(self.user)

        response = self.client.get(reverse("two_factor"))

        self.assertContains(response, "Replace authenticator app")
        self.assertContains(
            response, "Two-factor authentication is required for all accounts."
        )
        self.assertNotContains(response, "Turn off two-factor authentication")

    def test_removing_authenticator_leads_straight_back_to_setup(self):
        enable_two_factor(self.user)
        disable_url = reverse("two_factor_disable")

        self.assertContains(self.client.get(disable_url), "Replace your authenticator")
        response = self.client.post(disable_url, {"password": PASSWORD})

        self.assertRedirects(response, self.setup_url)
        self.assertFalse(two_factor.has_two_factor(self.user))
        self.assertRedirects(self.client.get(reverse("profile")), self.setup_url)
