"""Tests for enrolling in, and managing, two-factor authentication."""

from datetime import timedelta

import time_machine
from django.core import mail
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_static.models import StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts import two_factor
from accounts.factories import UserFactory
from accounts.models import CustomUser

PASSWORD = "testpassword123"


def current_code(device: TOTPDevice) -> str:
    """Return the code an authenticator app would show for the device right now."""
    token = totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits)
    return f"{token:0{device.digits}d}"


def create_user(**kwargs) -> CustomUser:
    user = UserFactory.create(**kwargs)
    user.set_password(PASSWORD)
    user.save()
    return user


def enable_two_factor(user: CustomUser) -> list[str]:
    """Enrol the user and return their recovery codes."""
    return two_factor.enable_two_factor(two_factor.get_or_create_pending_device(user))


class TwoFactorHelperTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()

    def test_pending_device_does_not_enable_two_factor(self):
        two_factor.get_or_create_pending_device(self.user)

        self.assertFalse(two_factor.has_two_factor(self.user))

    def test_pending_device_is_reused(self):
        first = two_factor.get_or_create_pending_device(self.user)
        second = two_factor.get_or_create_pending_device(self.user)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)

    def test_stale_pending_device_is_replaced(self):
        first = two_factor.get_or_create_pending_device(self.user)

        with time_machine.travel(
            timezone.now() + two_factor.PENDING_DEVICE_MAX_AGE + timedelta(minutes=1)
        ):
            second = two_factor.get_or_create_pending_device(self.user)

        self.assertNotEqual(first.key, second.key)
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)

    def test_replacing_stale_pending_device_keeps_confirmed_device(self):
        enable_two_factor(self.user)
        confirmed = TOTPDevice.objects.get(user=self.user)

        with time_machine.travel(
            timezone.now() + two_factor.PENDING_DEVICE_MAX_AGE + timedelta(minutes=1)
        ):
            two_factor.get_or_create_pending_device(self.user)

        self.assertTrue(TOTPDevice.objects.filter(pk=confirmed.pk).exists())

    def test_enable_confirms_device_and_creates_recovery_codes(self):
        codes = enable_two_factor(self.user)

        self.assertTrue(two_factor.has_two_factor(self.user))
        self.assertEqual(len(set(codes)), two_factor.RECOVERY_CODE_COUNT)
        self.assertEqual(
            two_factor.remaining_recovery_codes(self.user),
            two_factor.RECOVERY_CODE_COUNT,
        )

    def test_generate_recovery_codes_replaces_existing_codes(self):
        old_codes = enable_two_factor(self.user)

        new_codes = two_factor.generate_recovery_codes(self.user)

        self.assertEqual(StaticDevice.objects.filter(user=self.user).count(), 1)
        self.assertCountEqual(
            StaticToken.objects.filter(device__user=self.user).values_list(
                "token", flat=True
            ),
            new_codes,
        )
        self.assertFalse(set(old_codes) & set(new_codes))

    def test_verify_login_token_without_two_factor(self):
        self.assertIsNone(two_factor.verify_login_token(self.user, "123456"))

    def test_verify_login_token_without_recovery_codes(self):
        enable_two_factor(self.user)
        StaticDevice.objects.filter(user=self.user).delete()

        self.assertIsNone(two_factor.verify_login_token(self.user, "abcdefgh"))

    def test_disable_removes_devices_for_that_user_only(self):
        other_user = UserFactory.create()
        enable_two_factor(self.user)
        enable_two_factor(other_user)

        two_factor.disable_two_factor(self.user)

        self.assertFalse(two_factor.has_two_factor(self.user))
        self.assertEqual(two_factor.remaining_recovery_codes(self.user), 0)
        self.assertTrue(two_factor.has_two_factor(other_user))
        self.assertEqual(
            two_factor.remaining_recovery_codes(other_user),
            two_factor.RECOVERY_CODE_COUNT,
        )

    def test_qr_code_and_manual_key_describe_the_device(self):
        device = two_factor.get_or_create_pending_device(self.user)

        self.assertTrue(
            two_factor.get_qr_code_data_uri(device).startswith("data:image/svg+xml")
        )
        self.assertIn(
            f"secret={two_factor.get_manual_entry_key(device)}", device.config_url
        )
        self.assertIn("issuer=Djangonaut%20Space", device.config_url)


class TwoFactorOverviewViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.url = reverse("two_factor")

    def test_requires_login(self):
        response = self.client.get(self.url)

        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_shows_setup_link_when_disabled(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertContains(response, "Two-factor authentication is off")
        self.assertContains(response, reverse("two_factor_setup"))
        self.assertNotContains(response, reverse("two_factor_disable"))

    def test_shows_management_links_when_enabled(self):
        enable_two_factor(self.user)
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertContains(response, "Two-factor authentication is on")
        self.assertContains(response, "You have 10 of 10 unused codes left.")
        self.assertContains(response, reverse("two_factor_recovery_codes"))
        self.assertContains(response, reverse("two_factor_disable"))
        self.assertNotContains(response, reverse("two_factor_setup"))

    def test_profile_links_to_overview(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("profile"))

        self.assertContains(response, self.url)
        self.assertFalse(response.context["two_factor_enabled"])


@override_settings(ENVIRONMENT="production")
class TwoFactorSetupViewTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.url = reverse("two_factor_setup")

    def post_setup(self, token: str, password: str = PASSWORD):
        return self.client.post(self.url, {"token": token, "password": password})

    def test_requires_login(self):
        response = self.client.get(self.url)

        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")
        self.assertFalse(TOTPDevice.objects.exists())

    def test_get_shows_qr_code_and_setup_key(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        device = TOTPDevice.objects.get(user=self.user)
        self.assertFalse(device.confirmed)
        self.assertContains(response, "data:image/svg+xml")
        self.assertContains(response, two_factor.get_manual_entry_key(device))
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_reloading_keeps_the_same_secret(self):
        self.client.force_login(self.user)

        first = self.client.get(self.url)
        second = self.client.get(self.url)

        self.assertEqual(
            first.context["manual_entry_key"], second.context["manual_entry_key"]
        )

    def test_valid_code_enables_two_factor(self):
        self.client.force_login(self.user)
        self.client.get(self.url)
        device = TOTPDevice.objects.get(user=self.user)

        response = self.post_setup(current_code(device))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/two_factor_recovery_codes.html")
        self.assertTrue(two_factor.has_two_factor(self.user))
        codes = response.context["recovery_codes"]
        self.assertEqual(len(codes), two_factor.RECOVERY_CODE_COUNT)
        for code in codes:
            self.assertContains(response, code)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("turned on", mail.outbox[0].subject)

    def test_code_with_spaces_is_accepted(self):
        self.client.force_login(self.user)
        device = two_factor.get_or_create_pending_device(self.user)
        code = current_code(device)

        self.post_setup(f" {code[:3]} {code[3:]} ")

        self.assertTrue(two_factor.has_two_factor(self.user))

    def test_invalid_code_is_rejected(self):
        self.client.force_login(self.user)
        device = two_factor.get_or_create_pending_device(self.user)
        wrong_code = f"{(int(current_code(device)) + 1) % 10**6:06d}"

        response = self.post_setup(wrong_code)

        self.assertContains(response, "That code is not valid.")
        self.assertFalse(two_factor.has_two_factor(self.user))
        self.assertEqual(two_factor.remaining_recovery_codes(self.user), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_non_numeric_code_is_rejected(self):
        self.client.force_login(self.user)

        response = self.post_setup("abcdef")

        self.assertContains(response, "Enter the 6-digit code")
        self.assertFalse(two_factor.has_two_factor(self.user))

    def test_wrong_password_is_rejected_without_using_an_attempt(self):
        self.client.force_login(self.user)
        device = two_factor.get_or_create_pending_device(self.user)

        response = self.post_setup(current_code(device), password="wrong")

        self.assertContains(response, "Incorrect password.")
        self.assertFalse(two_factor.has_two_factor(self.user))
        device.refresh_from_db()
        self.assertEqual(device.throttling_failure_count, 0)

    def test_repeated_wrong_codes_are_throttled(self):
        self.client.force_login(self.user)
        device = two_factor.get_or_create_pending_device(self.user)

        with time_machine.travel(timezone.now(), tick=False) as traveller:
            self.post_setup("000000" if current_code(device) != "000000" else "111111")

            response = self.post_setup(current_code(device))
            self.assertContains(response, "Too many incorrect codes.")
            self.assertFalse(two_factor.has_two_factor(self.user))

            traveller.shift(timedelta(seconds=2))
            self.post_setup(current_code(device))
            self.assertTrue(two_factor.has_two_factor(self.user))

    def test_redirects_when_already_enabled(self):
        enable_two_factor(self.user)
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertRedirects(response, reverse("two_factor"))
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)


@override_settings(ENVIRONMENT="production")
class TwoFactorRecoveryCodesViewTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.url = reverse("two_factor_recovery_codes")

    def test_requires_login(self):
        response = self.client.post(self.url, {"password": PASSWORD})

        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_redirects_when_two_factor_is_disabled(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url, {"password": PASSWORD})

        self.assertRedirects(response, reverse("two_factor"))
        self.assertFalse(StaticDevice.objects.exists())

    def test_get_does_not_reveal_or_change_codes(self):
        codes = enable_two_factor(self.user)
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        for code in codes:
            self.assertNotContains(response, code)
        self.assertCountEqual(
            StaticToken.objects.filter(device__user=self.user).values_list(
                "token", flat=True
            ),
            codes,
        )

    def test_wrong_password_keeps_existing_codes(self):
        codes = enable_two_factor(self.user)
        self.client.force_login(self.user)

        response = self.client.post(self.url, {"password": "wrong"})

        self.assertContains(response, "Incorrect password.")
        self.assertCountEqual(
            StaticToken.objects.filter(device__user=self.user).values_list(
                "token", flat=True
            ),
            codes,
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_correct_password_replaces_and_shows_codes(self):
        old_codes = enable_two_factor(self.user)
        self.client.force_login(self.user)

        response = self.client.post(self.url, {"password": PASSWORD})

        new_codes = response.context["recovery_codes"]
        self.assertEqual(len(new_codes), two_factor.RECOVERY_CODE_COUNT)
        self.assertFalse(set(old_codes) & set(new_codes))
        for code in new_codes:
            self.assertContains(response, code)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("recovery codes", mail.outbox[0].subject)


@override_settings(ENVIRONMENT="production")
class TwoFactorDisableViewTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.url = reverse("two_factor_disable")

    def test_requires_login(self):
        response = self.client.post(self.url, {"password": PASSWORD})

        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_redirects_when_two_factor_is_disabled(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertRedirects(response, reverse("two_factor"))

    def test_wrong_password_keeps_two_factor_enabled(self):
        enable_two_factor(self.user)
        self.client.force_login(self.user)

        response = self.client.post(self.url, {"password": "wrong"})

        self.assertContains(response, "Incorrect password.")
        self.assertTrue(two_factor.has_two_factor(self.user))
        self.assertEqual(len(mail.outbox), 0)

    def test_correct_password_disables_two_factor(self):
        enable_two_factor(self.user)
        self.client.force_login(self.user)

        response = self.client.post(self.url, {"password": PASSWORD}, follow=True)

        self.assertRedirects(response, reverse("two_factor"))
        self.assertContains(response, "Two-factor authentication has been turned off.")
        self.assertFalse(two_factor.has_two_factor(self.user))
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.user).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("turned off", mail.outbox[0].subject)
