import json

import responses as rsps
from django.test import Client
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.factories import UserFactory
from accounts.tokens import account_activation_token
from conftest import BD_SETTINGS

_BASE_URL = "https://api.buttondown.email/v1"


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

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_activate_email_forwards_client_ip_to_buttondown(self):
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers/{self.user.email}", status=404)
        rsps.add(
            rsps.POST,
            f"{_BASE_URL}/subscribers",
            json={"id": "new-uuid"},
            status=201,
        )
        activate_url = reverse(
            "activate_account",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(self.user.pk)),
                "token": account_activation_token.make_token(self.user),
            },
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.client.get(activate_url, REMOTE_ADDR="203.0.113.5")

        create_call = next(call for call in rsps.calls if call.request.method == "POST")
        body = json.loads(create_call.request.body)
        self.assertEqual(body["ip_address"], "203.0.113.5")
