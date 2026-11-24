"""
Tests for two-factor authentication, which django-allauth provides.

These cover how allauth is wired into this project (routing, templates, emails,
the confirmed-email rule) and the routes that must not skip the code step.
"""

from allauth.account.models import EmailAddress
from allauth.core.context import request_context
from allauth.mfa.models import Authenticator
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.tests.two_factor_helpers import create_user
from accounts.tests.two_factor_helpers import current_code
from accounts.tests.two_factor_helpers import enable_two_factor
from accounts.tests.two_factor_helpers import reauthenticate
from accounts.tests.two_factor_helpers import recovery_codes
from accounts.tests.two_factor_helpers import submit_password
from accounts.tokens import account_activation_token
from accounts.two_factor import has_two_factor

ACTIVATE_URL = "/accounts/two-factor/totp/activate/"
CODE_URL = "/accounts/two-factor/authenticate/"


class TwoFactorTestCase(TestCase):
    def setUp(self):
        # allauth remembers used codes in the cache so they can't be replayed.
        cache.clear()
        self.user = create_user()


@override_settings(ENVIRONMENT="production")
class ActivationTests(TwoFactorTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def activate(self):
        reauthenticate(self.client)
        secret = self.client.get(ACTIVATE_URL).context["form"].secret
        # allauth sends its notification once the change is committed, which
        # in a TestCase is after the request (and its allauth context) is over.
        request = RequestFactory().get(ACTIVATE_URL)
        request.user = self.user
        with request_context(request), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(ACTIVATE_URL, {"code": current_code(secret)})
        return response

    def test_urls(self):
        self.assertEqual(reverse("mfa_index"), "/accounts/two-factor/")
        self.assertEqual(reverse("mfa_activate_totp"), ACTIVATE_URL)
        self.assertEqual(reverse("mfa_authenticate"), CODE_URL)

    def test_anonymous_user_is_sent_to_login(self):
        self.client.logout()

        response = self.client.get(reverse("mfa_index"))

        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('mfa_index')}"
        )

    def test_overview_uses_the_site_layout(self):
        response = self.client.get(reverse("mfa_index"))

        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, "An authenticator app is not active.")

    def test_setup_asks_for_the_password_first(self):
        response = self.client.get(ACTIVATE_URL)

        self.assertRedirects(
            response, f"{reverse('account_reauthenticate')}?next={ACTIVATE_URL}"
        )

    def test_wrong_password_does_not_reach_setup(self):
        self.client.post(reverse("account_reauthenticate"), {"password": "wrong"})

        response = self.client.get(ACTIVATE_URL)

        self.assertEqual(response.status_code, 302)

    def test_setup_shows_qr_code_and_secret(self):
        reauthenticate(self.client)

        response = self.client.get(ACTIVATE_URL)

        self.assertContains(response, "data:image/svg+xml;base64,")
        self.assertContains(response, response.context["form"].secret)
        self.assertIn("issuer=Djangonaut%20Space", response.context["totp_url"])

    def test_valid_code_turns_two_factor_on_and_shows_recovery_codes(self):
        response = self.activate()

        self.assertRedirects(response, reverse("mfa_view_recovery_codes"))
        self.assertTrue(has_two_factor(self.user))
        codes = recovery_codes(self.user)
        self.assertEqual(len(codes), 10)
        self.assertContains(self.client.get(response.url), codes[0])

    def test_user_is_emailed_when_two_factor_is_turned_on(self):
        self.activate()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("Authenticator App Activated", mail.outbox[0].subject)

    @override_settings(ENVIRONMENT="staging")
    def test_notification_is_not_emailed_to_real_users_outside_production(self):
        self.activate()

        self.assertEqual(mail.outbox, [])

    @override_settings(
        ENVIRONMENT="staging", ALLOWED_EMAILS_FOR_TESTING=["astronaut@example.com"]
    )
    def test_notification_is_emailed_to_allowed_testers_outside_production(self):
        self.activate()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_notification_goes_to_the_email_on_the_user_record(self):
        """Even if allauth's copy of the address has fallen behind."""
        EmailAddress.objects.filter(user=self.user).update(email="old@example.com")

        self.activate()

        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_wrong_code_does_not_turn_two_factor_on(self):
        reauthenticate(self.client)
        self.client.get(ACTIVATE_URL)

        response = self.client.post(ACTIVATE_URL, {"code": "000000"})

        self.assertContains(response, "Incorrect code.")
        self.assertFalse(has_two_factor(self.user))

    def test_unconfirmed_email_cannot_turn_two_factor_on(self):
        self.user.profile.email_confirmed = False
        self.user.profile.save()
        reauthenticate(self.client)

        response = self.client.get(ACTIVATE_URL, follow=True)

        self.assertRedirects(response, reverse("mfa_index"))
        self.assertContains(response, "until you have verified your email address")

    def test_turning_off_removes_authenticator_and_recovery_codes(self):
        enable_two_factor(self.user)
        reauthenticate(self.client)

        response = self.client.post(reverse("mfa_deactivate_totp"))

        self.assertRedirects(response, reverse("mfa_index"))
        self.assertFalse(Authenticator.objects.filter(user=self.user).exists())
        self.assertIn("Authenticator App Deactivated", mail.outbox[0].subject)

    def test_turning_off_asks_for_the_password_first(self):
        enable_two_factor(self.user)

        response = self.client.post(reverse("mfa_deactivate_totp"))

        self.assertIn(reverse("account_reauthenticate"), response.url)
        self.assertTrue(has_two_factor(self.user))

    def test_recovery_codes_can_be_replaced(self):
        enable_two_factor(self.user)
        old_codes = recovery_codes(self.user)
        reauthenticate(self.client)

        self.client.post(reverse("mfa_generate_recovery_codes"))

        new_codes = recovery_codes(self.user)
        self.assertEqual(len(new_codes), 10)
        self.assertNotEqual(new_codes, old_codes)

    def test_profile_shows_whether_two_factor_is_on(self):
        self.assertContains(self.client.get(reverse("profile")), "fa-x")

        enable_two_factor(self.user)

        response = self.client.get(reverse("profile"))
        self.assertContains(response, reverse("mfa_index"))
        self.assertTrue(response.context["two_factor_enabled"])

    def test_recovery_codes_alone_do_not_count_as_two_factor(self):
        enable_two_factor(self.user)
        Authenticator.objects.filter(
            user=self.user, type=Authenticator.Type.TOTP
        ).delete()

        self.assertFalse(has_two_factor(self.user))


class LoginWithTwoFactorTests(TwoFactorTestCase):
    def setUp(self):
        super().setUp()
        self.secret = enable_two_factor(self.user)

    def assertNotLoggedIn(self):
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.client.get(reverse("profile")).status_code, 302)

    def test_password_alone_does_not_log_in(self):
        response = submit_password(self.client, self.user)

        self.assertRedirects(response, CODE_URL)
        self.assertNotLoggedIn()

    def test_code_page_uses_the_site_layout(self):
        submit_password(self.client, self.user)

        response = self.client.get(CODE_URL)

        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, "protected by two-factor authentication")

    def test_authenticator_code_completes_login(self):
        submit_password(self.client, self.user, next="/accounts/availability/")

        response = self.client.post(CODE_URL, {"code": current_code(self.secret)})

        self.assertRedirects(response, reverse("availability"))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))

    def test_wrong_code_is_rejected(self):
        submit_password(self.client, self.user)

        response = self.client.post(CODE_URL, {"code": "000000"})

        self.assertContains(response, "Incorrect code.")
        self.assertNotLoggedIn()

    def test_authenticator_code_cannot_be_replayed(self):
        code = current_code(self.secret)
        submit_password(self.client, self.user)
        self.client.post(CODE_URL, {"code": code})
        self.client.post(reverse("logout"))

        submit_password(self.client, self.user)
        response = self.client.post(CODE_URL, {"code": code})

        self.assertContains(response, "Incorrect code.")
        self.assertNotLoggedIn()

    def test_recovery_code_works_once(self):
        code = recovery_codes(self.user)[0]
        submit_password(self.client, self.user)

        response = self.client.post(CODE_URL, {"code": code})

        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(len(recovery_codes(self.user)), 9)

        self.client.post(reverse("logout"))
        submit_password(self.client, self.user)
        response = self.client.post(CODE_URL, {"code": code})

        self.assertContains(response, "Incorrect code.")
        self.assertNotLoggedIn()

    def test_code_page_needs_a_password_first(self):
        response = self.client.get(CODE_URL)

        self.assertRedirects(response, reverse("login"))

    def test_cancelling_discards_the_accepted_password(self):
        submit_password(self.client, self.user)

        self.client.post(reverse("account_logout"))

        self.assertRedirects(self.client.get(CODE_URL), reverse("login"))

    def test_user_without_two_factor_is_not_asked_for_a_code(self):
        other = create_user("other")

        response = submit_password(self.client, other)

        self.assertRedirects(response, reverse("profile"))


class OtherWaysInTests(TwoFactorTestCase):
    """Routes besides the login form must not stand in for the second factor."""

    def activation_url(self) -> str:
        return reverse(
            "activate_account",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(self.user.pk)),
                "token": account_activation_token.make_token(self.user),
            },
        )

    def test_email_confirmation_link_logs_in_without_two_factor(self):
        response = self.client.get(self.activation_url())

        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))

    def test_email_confirmation_link_does_not_log_in_with_two_factor(self):
        enable_two_factor(self.user)
        self.user.profile.email_confirmed = False
        self.user.profile.save()

        response = self.client.get(self.activation_url(), follow=True)

        self.assertRedirects(response, reverse("login"))
        self.assertContains(response, "Your email address is confirmed. Please log in.")
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.email_confirmed)

    def test_password_reset_does_not_log_in_or_remove_two_factor(self):
        enable_two_factor(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        set_password_url = self.client.get(
            reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        ).url

        response = self.client.post(
            set_password_url,
            {
                "new_password1": "a-brand-new-passphrase",
                "new_password2": "a-brand-new-passphrase",
            },
        )

        self.assertRedirects(response, reverse("password_reset_complete"))
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertTrue(has_two_factor(self.user))
        response = self.client.post(
            reverse("login"),
            {"login": self.user.username, "password": "a-brand-new-passphrase"},
        )
        self.assertRedirects(response, CODE_URL)
