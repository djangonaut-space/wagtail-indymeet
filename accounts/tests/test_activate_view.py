from django.test import Client, TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.factories import UserFactory
from accounts.tokens import account_activation_token


class ActivateViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()

    def test_user_does_not_exist(self):
        activate_url = reverse(
            "activate_account",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes("500")),
                "token": account_activation_token.make_token(self.user),
            },
        )
        response = self.client.get(activate_url, follow=True)
        self.assertRedirects(response, reverse("signup"))
        self.assertContains(response, "Your confirmation link is invalid.")
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.email_confirmed)

    def test_invalid_token(self):
        activate_url = reverse(
            "activate_account",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(self.user.pk)),
                "token": "INVALID_TOKEN",
            },
        )
        response = self.client.get(activate_url, follow=True)
        self.assertRedirects(response, reverse("signup"))
        self.assertContains(response, "Your confirmation link is invalid.")
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.email_confirmed)

    def test_activate_email(self):
        activate_url = reverse(
            "activate_account",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(self.user.pk)),
                "token": account_activation_token.make_token(self.user),
            },
        )
        response = self.client.get(activate_url)
        self.assertRedirects(response, reverse("profile"))
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.email_confirmed)
