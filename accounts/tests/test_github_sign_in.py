"""
Tests for signing in with GitHub, which django-allauth provides.

GitHub itself is replaced with canned HTTP responses; everything else is the
real allauth flow, so these cover how it is configured for this project.
"""

from urllib.parse import parse_qs
from urllib.parse import urlparse

import responses
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import SESSION_KEY
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from accounts.tests.two_factor_helpers import create_user
from accounts.tests.two_factor_helpers import current_code
from accounts.tests.two_factor_helpers import enable_two_factor
from accounts.tests.two_factor_helpers import reauthenticate

GITHUB_LOGIN_URL = "/accounts/github/login/"
GITHUB_CALLBACK_URL = "/accounts/github/login/callback/"
SIGNUP_URL = "/accounts/social/signup/"
CONNECTIONS_URL = "/accounts/social/"

GITHUB_SETTINGS = {"github": {"APP": {"client_id": "client-id", "secret": "secret"}}}


@override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_SETTINGS, ENVIRONMENT="production")
class GitHubTestCase(TestCase):
    def setUp(self):
        cache.clear()

    def github_sign_in(
        self,
        *,
        uid: int = 583231,
        login: str = "octocat",
        name: str = "Mona Octocat",
        email: str | None = "octocat@example.com",
        verified: bool = True,
        process: str = "login",
    ):
        """Go to GitHub and come back as the given GitHub user."""
        response = self.client.post(f"{GITHUB_LOGIN_URL}?process={process}")
        authorize_url = urlparse(response.url)
        self.assertEqual(authorize_url.netloc, "github.com")
        state = parse_qs(authorize_url.query)["state"][0]

        with responses.RequestsMock() as github:
            github.post(
                "https://github.com/login/oauth/access_token",
                json={"access_token": "token", "token_type": "bearer"},
            )
            github.get(
                "https://api.github.com/user",
                json={"id": uid, "login": login, "name": name, "email": None},
            )
            github.get(
                "https://api.github.com/user/emails",
                json=(
                    [{"email": email, "primary": True, "verified": verified}]
                    if email
                    else []
                ),
            )
            return self.client.get(
                GITHUB_CALLBACK_URL, {"code": "code", "state": state}
            )

    def signup_data(self, **overrides) -> dict:
        data = {
            "username": "octocat",
            "email": "octocat@example.com",
            "first_name": "Mona",
            "last_name": "Octocat",
            "email_consent": "on",
            "accepted_coc": "on",
        }
        data.update(overrides)
        return data


class GitHubOfferedTests(GitHubTestCase):
    def test_urls(self):
        self.assertEqual(reverse("github_login"), GITHUB_LOGIN_URL)
        self.assertEqual(reverse("github_callback"), GITHUB_CALLBACK_URL)
        self.assertEqual(reverse("socialaccount_signup"), SIGNUP_URL)
        self.assertEqual(reverse("socialaccount_connections"), CONNECTIONS_URL)

    def test_login_page_offers_github(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, "Continue with GitHub")
        self.assertContains(response, GITHUB_LOGIN_URL)

    def test_profile_links_to_github_connections(self):
        self.client.force_login(create_user())

        response = self.client.get(reverse("profile"))

        self.assertContains(response, CONNECTIONS_URL)

    @override_settings(SOCIALACCOUNT_PROVIDERS={"github": {}})
    def test_nothing_is_offered_without_credentials(self):
        self.client.force_login(create_user())

        self.assertNotContains(self.client.get(reverse("profile")), CONNECTIONS_URL)
        self.assertEqual(self.client.post(GITHUB_LOGIN_URL).status_code, 404)

    def test_visiting_the_github_login_asks_before_leaving_the_site(self):
        response = self.client.get(GITHUB_LOGIN_URL)

        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, "Sign In Via GitHub")


class GitHubSignupTests(GitHubTestCase):
    def test_new_github_user_is_asked_to_complete_signup(self):
        response = self.github_sign_in()

        self.assertRedirects(response, SIGNUP_URL)
        self.assertFalse(CustomUser.objects.exists())
        response = self.client.get(SIGNUP_URL)
        self.assertTemplateUsed(response, "base.html")
        self.assertEqual(response.context["form"].initial["username"], "octocat")
        self.assertEqual(
            response.context["form"].initial["email"], "octocat@example.com"
        )
        self.assertContains(response, "Accept CoC*")

    def test_completing_signup_creates_a_logged_in_account(self):
        self.github_sign_in()

        response = self.client.post(
            SIGNUP_URL, self.signup_data(receive_newsletter="on")
        )

        self.assertRedirects(response, reverse("profile"))
        user = CustomUser.objects.get()
        self.assertEqual(self.client.session[SESSION_KEY], str(user.pk))
        self.assertEqual(user.username, "octocat")
        self.assertEqual(user.email, "octocat@example.com")
        self.assertEqual(user.get_full_name(), "Mona Octocat")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.profile.accepted_coc)
        self.assertTrue(user.profile.receiving_newsletter)
        self.assertEqual(user.profile.github_username, "octocat")
        self.assertTrue(SocialAccount.objects.filter(user=user, uid="583231").exists())

    def test_email_verified_by_github_needs_no_confirmation(self):
        self.github_sign_in()

        self.client.post(SIGNUP_URL, self.signup_data())

        self.assertTrue(CustomUser.objects.get().profile.email_confirmed)
        self.assertEqual(mail.outbox, [])

    def test_email_not_verified_by_github_must_be_confirmed(self):
        self.github_sign_in(verified=False)

        self.client.post(SIGNUP_URL, self.signup_data())

        user = CustomUser.objects.get()
        self.assertFalse(user.profile.email_confirmed)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["octocat@example.com"])
        self.assertIn("/accounts/activate/", mail.outbox[0].body)

    def test_email_from_github_cannot_be_replaced_during_signup(self):
        self.github_sign_in()

        self.assertTrue(
            self.client.get(SIGNUP_URL).context["form"]["email"].field.disabled
        )
        self.client.post(SIGNUP_URL, self.signup_data(email="other@example.com"))

        self.assertEqual(CustomUser.objects.get().email, "octocat@example.com")

    def test_email_is_asked_for_and_confirmed_when_github_shares_none(self):
        self.github_sign_in(email=None)

        self.assertFalse(
            self.client.get(SIGNUP_URL).context["form"]["email"].field.disabled
        )
        self.client.post(SIGNUP_URL, self.signup_data(email="typed@example.com"))

        user = CustomUser.objects.get()
        self.assertEqual(user.email, "typed@example.com")
        self.assertFalse(user.profile.email_confirmed)
        self.assertEqual(mail.outbox[0].to, ["typed@example.com"])
        self.assertEqual(
            list(EmailAddress.objects.values_list("email", "verified")),
            [("typed@example.com", False)],
        )

    def test_code_of_conduct_and_email_consent_are_required(self):
        self.github_sign_in()
        for field in ("accepted_coc", "email_consent"):
            with self.subTest(field=field):
                data = self.signup_data()
                del data[field]

                response = self.client.post(SIGNUP_URL, data)

                self.assertIn(field, response.context["form"].errors)
                self.assertFalse(CustomUser.objects.exists())

    def test_email_of_an_existing_account_is_refused(self):
        create_user("existing", email="octocat@example.com")
        self.github_sign_in()

        response = self.client.post(SIGNUP_URL, self.signup_data())

        self.assertContains(response, "An account already exists with this email")
        self.assertEqual(CustomUser.objects.count(), 1)
        self.assertFalse(SocialAccount.objects.exists())

    def test_username_of_an_existing_account_is_refused(self):
        create_user("octocat", email="someone@example.com")
        self.github_sign_in()

        response = self.client.post(SIGNUP_URL, self.signup_data())

        self.assertIn("username", response.context["form"].errors)
        self.assertEqual(CustomUser.objects.count(), 1)

    def test_signup_page_needs_a_github_sign_in_first(self):
        response = self.client.get(SIGNUP_URL)

        self.assertRedirects(response, reverse("login"))


class GitHubLoginTests(GitHubTestCase):
    def setUp(self):
        super().setUp()
        self.user = create_user("octocat", email="octocat@example.com")
        SocialAccount.objects.create(user=self.user, provider="github", uid="583231")

    def test_connected_user_is_logged_in(self):
        response = self.github_sign_in()

        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))

    def test_account_is_matched_by_github_id_not_by_email(self):
        """Someone else whose GitHub account lists this email gets no access."""
        response = self.github_sign_in(uid=999, login="impostor")

        self.assertRedirects(response, SIGNUP_URL)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_two_factor_code_is_still_required(self):
        secret = enable_two_factor(self.user)

        response = self.github_sign_in()

        self.assertRedirects(response, reverse("mfa_authenticate"))
        self.assertNotIn(SESSION_KEY, self.client.session)
        response = self.client.post(
            reverse("mfa_authenticate"), {"code": current_code(secret)}
        )
        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))

    def test_deactivated_user_is_not_logged_in(self):
        self.user.is_active = False
        self.user.save()

        response = self.github_sign_in()

        self.assertRedirects(response, reverse("account_inactive"))
        self.assertNotIn(SESSION_KEY, self.client.session)


class GitHubConnectTests(GitHubTestCase):
    def setUp(self):
        super().setUp()
        self.user = create_user()
        self.client.force_login(self.user)

    def test_connections_page_uses_the_site_layout(self):
        response = self.client.get(CONNECTIONS_URL)

        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, f"{GITHUB_LOGIN_URL}?process=connect")

    def test_existing_user_can_connect_github_after_confirming_their_password(self):
        response = self.github_sign_in(process="connect")

        self.assertRedirects(response, reverse("account_reauthenticate"))
        self.assertFalse(SocialAccount.objects.exists())

        response = reauthenticate(self.client)

        self.assertRedirects(response, CONNECTIONS_URL)
        self.assertTrue(
            SocialAccount.objects.filter(user=self.user, uid="583231").exists()
        )
        self.assertEqual(CustomUser.objects.count(), 1)
        self.assertIn("Third-Party Account Connected", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_github_account_of_another_user_cannot_be_connected(self):
        other = create_user("other")
        SocialAccount.objects.create(user=other, provider="github", uid="583231")
        reauthenticate(self.client)

        self.github_sign_in(process="connect")

        self.assertFalse(SocialAccount.objects.filter(user=self.user).exists())

    def test_connected_account_is_listed_and_can_be_removed(self):
        account = SocialAccount.objects.create(
            user=self.user, provider="github", uid="583231"
        )
        reauthenticate(self.client)

        self.assertContains(self.client.get(CONNECTIONS_URL), "GitHub")
        response = self.client.post(CONNECTIONS_URL, {"account": account.pk})

        self.assertRedirects(response, CONNECTIONS_URL)
        self.assertFalse(SocialAccount.objects.exists())

    def test_removing_github_asks_for_the_password_first(self):
        account = SocialAccount.objects.create(
            user=self.user, provider="github", uid="583231"
        )

        self.client.post(CONNECTIONS_URL, {"account": account.pk})

        self.assertTrue(SocialAccount.objects.exists())
