"""Tests for logging in, which django-allauth handles."""

from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.tests.two_factor_helpers import create_user
from accounts.tests.two_factor_helpers import PASSWORD
from accounts.tests.two_factor_helpers import submit_password


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()

    def test_correct_password_logs_in(self):
        response = submit_password(self.client, self.user)

        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))

    def test_login_continues_to_the_requested_page(self):
        response = submit_password(
            self.client, self.user, next="/accounts/availability/"
        )

        self.assertRedirects(response, reverse("availability"))

    def test_login_ignores_a_next_url_on_another_site(self):
        response = submit_password(self.client, self.user, next="https://evil.example/")

        self.assertRedirects(response, reverse("profile"))

    def test_logging_in_shows_no_message(self):
        response = self.client.post(
            reverse("login"),
            {"login": self.user.username, "password": PASSWORD},
            follow=True,
        )

        self.assertEqual(list(response.context["messages"]), [])

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            reverse("login"), {"login": self.user.username, "password": "wrong"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not correct")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()

        submit_password(self.client, self.user)

        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_login_page_links_to_password_reset(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, reverse("password_reset"))
        self.assertContains(response, "Forgotten your password?")

    def test_github_is_not_offered_without_credentials(self):
        response = self.client.get(reverse("login"))

        self.assertNotContains(response, "Continue with GitHub")


class UnusedAllauthPagesTests(TestCase):
    """Signup, email and password management stay this project's own pages."""

    def test_allauth_account_pages_are_not_routed(self):
        self.client.force_login(create_user())
        for path in (
            "/accounts/password/reset/",
            "/accounts/password/change/",
            "/accounts/email/",
            "/accounts/confirm-email/",
            "/accounts/login/code/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_signup_is_the_project_signup_form(self):
        response = self.client.get(reverse("account_signup"))

        self.assertTemplateUsed(response, "registration/signup.html")


class AdminLoginTests(TestCase):
    """Neither admin's own login form may be used to skip the two-factor step."""

    ADMIN_LOGINS = {
        "/django-admin/login/": "/django-admin/",
        "/admin/login/": "/admin/",
    }

    @classmethod
    def setUpTestData(cls):
        cls.superuser = create_user("admin", is_staff=True, is_superuser=True)

    def test_anonymous_user_is_sent_to_the_main_login(self):
        for login_url, index_url in self.ADMIN_LOGINS.items():
            with self.subTest(login_url=login_url):
                response = self.client.get(login_url)

                self.assertRedirects(response, f"{reverse('login')}?next={index_url}")

    def test_requested_admin_page_is_kept(self):
        response = self.client.get("/django-admin/login/?next=/django-admin/auth/")

        self.assertRedirects(response, f"{reverse('login')}?next=/django-admin/auth/")

    def test_admin_pages_lead_to_the_main_login(self):
        for index_url in self.ADMIN_LOGINS.values():
            with self.subTest(index_url=index_url):
                response = self.client.get(index_url, follow=True)

                self.assertEqual(response.request["PATH_INFO"], reverse("login"))
                self.assertTemplateUsed(response, "account/login.html")

    def test_posting_credentials_to_an_admin_login_does_not_log_in(self):
        for login_url in self.ADMIN_LOGINS:
            with self.subTest(login_url=login_url):
                response = self.client.post(
                    login_url,
                    {"username": self.superuser.username, "password": PASSWORD},
                )

                self.assertEqual(response.status_code, 302)
                self.assertNotIn(SESSION_KEY, self.client.session)

    def test_signed_in_admin_is_sent_to_the_admin(self):
        self.client.force_login(self.superuser)
        for login_url, index_url in self.ADMIN_LOGINS.items():
            with self.subTest(login_url=login_url):
                self.assertRedirects(
                    self.client.get(login_url),
                    index_url,
                    fetch_redirect_response=False,
                )

    def test_signed_in_user_without_admin_access_is_refused(self):
        self.client.force_login(create_user("member"))
        for login_url in self.ADMIN_LOGINS:
            with self.subTest(login_url=login_url):
                self.assertEqual(self.client.get(login_url).status_code, 403)

    def test_wagtail_access_needs_its_own_permission(self):
        staff = create_user("staff", is_staff=True)
        self.client.force_login(staff)

        self.assertEqual(self.client.get("/admin/login/").status_code, 403)

        staff.user_permissions.add(Permission.objects.get(codename="access_admin"))

        self.assertRedirects(
            self.client.get("/admin/login/"), "/admin/", fetch_redirect_response=False
        )
