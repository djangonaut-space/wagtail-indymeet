from django.test import TestCase
from django.urls import reverse
from accounts.factories import ProfileFactory


class LoginViewTest(TestCase):
    """Test for redirect authenticated user when next is provided"""

    def setUp(self):
        profile = ProfileFactory.create(user__username="test")
        self.user = profile.user

    def test_authenticated_user_is_redirected_to_next(self):
        self.client.force_login(self.user)
        url = reverse("login") + "?next=/my-sessions/"
        response = self.client.get(url)
        self.assertRedirects(response, "/my-sessions/")

    def test_authenticated_user_wihtout_next_is_redirect_to_default(self):
        self.client.force_login(self.user)
        url = reverse("login")
        response = self.client.get(url)
        self.assertRedirects(response, "/accounts/profile/")

    def test_unauthenticated_user_sees_login_form(self):
        url = reverse("login") + "?next=/my-sessions/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/login.html")
