"""Tests for the two-step login and the routes that must not bypass it."""

from datetime import timedelta

import time_machine
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts import two_factor
from accounts.tests.test_two_factor import create_user
from accounts.tests.test_two_factor import current_code
from accounts.tests.test_two_factor import enable_two_factor
from accounts.tests.test_two_factor import PASSWORD
from accounts.tokens import account_activation_token


class TwoFactorLoginTestCase(TestCase):
    """Base class providing a user with two-factor authentication enabled."""

    def setUp(self):
        self.user = create_user()
        self.recovery_codes = enable_two_factor(self.user)
        self.device = TOTPDevice.objects.get(user=self.user)
        self.login_url = reverse("login")
        self.verify_url = reverse("two_factor_verify")

    def submit_password(self, password: str = PASSWORD, **extra):
        return self.client.post(
            self.login_url,
            {"username": self.user.username, "password": password, **extra},
        )

    def submit_code(self, token: str, **kwargs):
        return self.client.post(self.verify_url, {"token": token}, **kwargs)

    def assertLoggedIn(self):
        self.assertEqual(self.client.session.get(SESSION_KEY), str(self.user.pk))

    def assertNotLoggedIn(self):
        self.assertNotIn(SESSION_KEY, self.client.session)


class PasswordStepTests(TwoFactorLoginTestCase):
    def test_user_without_two_factor_logs_in_directly(self):
        two_factor.disable_two_factor(self.user)

        response = self.submit_password()

        self.assertRedirects(response, reverse("profile"))
        self.assertLoggedIn()

    def test_user_with_two_factor_is_sent_to_code_step_without_logging_in(self):
        response = self.submit_password()

        self.assertRedirects(response, self.verify_url)
        self.assertNotLoggedIn()

    def test_pending_setup_does_not_trigger_code_step(self):
        two_factor.disable_two_factor(self.user)
        two_factor.get_or_create_pending_device(self.user)

        response = self.submit_password()

        self.assertRedirects(response, reverse("profile"))
        self.assertLoggedIn()

    def test_wrong_password_does_not_reach_code_step(self):
        response = self.submit_password("wrong")

        self.assertEqual(response.status_code, 200)
        self.assertNotLoggedIn()
        self.assertRedirects(self.client.get(self.verify_url), self.login_url)


class CodeStepTests(TwoFactorLoginTestCase):
    def test_requires_password_step_first(self):
        response = self.submit_code(current_code(self.device))

        self.assertRedirects(response, self.login_url)
        self.assertNotLoggedIn()

    def test_valid_code_completes_login(self):
        self.submit_password()

        response = self.submit_code(current_code(self.device))

        self.assertRedirects(response, reverse("profile"))
        self.assertLoggedIn()
        self.assertEqual(
            self.client.session[DEVICE_ID_SESSION_KEY], self.device.persistent_id
        )
        self.assertNotIn(two_factor.PENDING_LOGIN_SESSION_KEY, self.client.session)

    def test_redirects_to_next_after_code_step(self):
        next_url = reverse("availability")
        self.submit_password(next=next_url)

        response = self.submit_code(current_code(self.device))

        self.assertRedirects(response, next_url)

    def test_external_next_is_ignored(self):
        self.submit_password(next="https://example.com/")

        response = self.submit_code(current_code(self.device))

        self.assertRedirects(response, reverse("profile"))

    def test_wrong_code_does_not_log_in(self):
        self.submit_password()
        wrong_code = f"{(int(current_code(self.device)) + 1) % 10**6:06d}"

        response = self.submit_code(wrong_code)

        self.assertContains(response, "That code is not valid.")
        self.assertNotLoggedIn()

    def test_repeated_wrong_codes_are_throttled(self):
        self.submit_password()

        with time_machine.travel(timezone.now(), tick=False) as traveller:
            self.submit_code("not-a-real-code")
            self.submit_code("000000" if current_code(self.device) != "000000" else "1")

            throttled_totp = self.submit_code(current_code(self.device))
            throttled_recovery = self.submit_code(self.recovery_codes[0])
            self.assertContains(throttled_totp, "Too many incorrect codes.")
            self.assertContains(throttled_recovery, "Too many incorrect codes.")
            self.assertNotLoggedIn()

            traveller.shift(timedelta(seconds=2))
            self.submit_code(current_code(self.device))
            self.assertLoggedIn()

    def test_code_cannot_be_replayed(self):
        with time_machine.travel(timezone.now(), tick=False):
            code = current_code(self.device)
            self.submit_password()
            self.submit_code(code)
            self.assertLoggedIn()
            self.client.logout()

            self.submit_password()
            response = self.submit_code(code)

            self.assertContains(response, "That code is not valid.")
            self.assertNotLoggedIn()

    def test_recovery_code_completes_login_and_is_consumed(self):
        self.submit_password()

        response = self.submit_code(self.recovery_codes[0], follow=True)

        self.assertLoggedIn()
        self.assertContains(
            response, "You logged in with a recovery code. You have 9 recovery codes"
        )
        self.assertEqual(two_factor.remaining_recovery_codes(self.user), 9)

    def test_recovery_code_cannot_be_reused(self):
        self.submit_password()
        self.submit_code(self.recovery_codes[0])
        self.client.logout()
        self.submit_password()

        response = self.submit_code(self.recovery_codes[0])

        self.assertContains(response, "That code is not valid.")
        self.assertNotLoggedIn()

    def test_recovery_code_ignores_case_and_spacing(self):
        self.submit_password()
        code = self.recovery_codes[0].upper()

        self.submit_code(f" {code[:4]} {code[4:]} ")

        self.assertLoggedIn()

    def test_code_from_another_user_is_rejected(self):
        other_user = create_user()
        other_codes = enable_two_factor(other_user)
        other_device = TOTPDevice.objects.get(user=other_user)
        self.submit_password()

        self.submit_code(other_codes[0])
        self.assertNotLoggedIn()

        with time_machine.travel(timezone.now() + timedelta(seconds=5)):
            self.submit_code(current_code(other_device))
            self.assertNotLoggedIn()

    def test_password_step_expires(self):
        self.submit_password()

        with time_machine.travel(
            timezone.now() + timedelta(seconds=two_factor.PENDING_LOGIN_MAX_AGE + 1)
        ):
            response = self.submit_code(current_code(self.device))

        self.assertRedirects(response, self.login_url)
        self.assertNotLoggedIn()

    def test_password_step_is_void_once_two_factor_is_removed(self):
        self.submit_password()
        two_factor.disable_two_factor(self.user)

        response = self.client.get(self.verify_url)

        self.assertRedirects(response, self.login_url)
        self.assertNotLoggedIn()

    def test_password_step_is_void_once_user_is_deactivated(self):
        self.submit_password()
        self.user.is_active = False
        self.user.save()

        response = self.submit_code(current_code(self.device))

        self.assertRedirects(response, self.login_url)
        self.assertNotLoggedIn()


class TwoFactorBypassTests(TwoFactorLoginTestCase):
    """Routes that sign users in, or could, without the code step."""

    def activation_url(self) -> str:
        return reverse(
            "activate_account",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(self.user.pk)),
                "token": account_activation_token.make_token(self.user),
            },
        )

    def test_activation_link_confirms_email_without_logging_in(self):
        response = self.client.get(self.activation_url(), follow=True)

        self.assertRedirects(response, self.login_url)
        self.assertContains(response, "Your email address is confirmed.")
        self.assertNotLoggedIn()
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.email_confirmed)

    def test_activation_link_still_logs_in_users_without_two_factor(self):
        two_factor.disable_two_factor(self.user)

        response = self.client.get(self.activation_url())

        self.assertRedirects(response, reverse("profile"))
        self.assertLoggedIn()

    def test_password_reset_does_not_log_in_or_remove_two_factor(self):
        url = reverse(
            "password_reset_confirm",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(self.user.pk)),
                "token": default_token_generator.make_token(self.user),
            },
        )
        set_password_url = self.client.get(url).url

        response = self.client.post(
            set_password_url,
            {"new_password1": "a-new-Passw0rd!", "new_password2": "a-new-Passw0rd!"},
        )

        self.assertRedirects(response, reverse("password_reset_complete"))
        self.assertNotLoggedIn()
        self.assertTrue(two_factor.has_two_factor(self.user))
        self.assertRedirects(self.submit_password("a-new-Passw0rd!"), self.verify_url)

    def test_admin_login_pages_redirect_anonymous_users_to_main_login(self):
        for admin_url in ("/django-admin/", "/admin/"):
            with self.subTest(admin_url=admin_url):
                response = self.client.get(admin_url, follow=True)

                self.assertEqual(
                    response.redirect_chain[-1][0].split("?")[0], self.login_url
                )
                self.assertEqual(response.context["next"], admin_url)

    def test_admin_login_pages_do_not_accept_credentials(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        for admin_login_url in ("/django-admin/login/", "/admin/login/"):
            with self.subTest(admin_login_url=admin_login_url):
                response = self.client.post(
                    admin_login_url,
                    {"username": self.user.username, "password": PASSWORD},
                )

                self.assertEqual(response.status_code, 405)
                self.assertNotLoggedIn()

    def test_signed_in_users_without_admin_access_can_switch_account(self):
        two_factor.disable_two_factor(self.user)
        admin = create_user(is_staff=True, is_superuser=True)
        self.client.force_login(self.user)

        for admin_url in ("/django-admin/", "/admin/"):
            with self.subTest(admin_url=admin_url):
                response = self.client.get(admin_url, follow=True)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "have access to this page")
                self.assertTemplateUsed(response, "registration/login.html")

        login_url, _status = response.redirect_chain[-1]
        response = self.client.post(
            login_url,
            {"username": admin.username, "password": PASSWORD, "next": "/admin/"},
        )

        self.assertRedirects(response, "/admin/", fetch_redirect_response=False)
        self.assertEqual(self.client.session[SESSION_KEY], str(admin.pk))

    def test_login_page_redirects_signed_in_users_by_default(self):
        self.client.force_login(self.user)

        response = self.client.get(self.login_url)

        self.assertRedirects(response, reverse("profile"))

    def test_admin_login_pages_send_signed_in_admins_to_the_admin(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)

        self.assertRedirects(
            self.client.get("/django-admin/login/"),
            reverse("admin:index"),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get("/admin/login/"),
            reverse("wagtailadmin_home"),
            fetch_redirect_response=False,
        )

    def test_staff_reach_django_admin_only_after_code_step(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        admin_index = reverse("admin:index")

        self.submit_password(next=admin_index)
        self.assertRedirects(
            self.client.get(admin_index),
            f"/django-admin/login/?next={admin_index}",
            fetch_redirect_response=False,
        )

        response = self.submit_code(current_code(self.device))
        self.assertRedirects(response, admin_index)
