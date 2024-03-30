from __future__ import annotations

from django.core import mail
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from home.factories import UserFactory


class AuthViewTests(TestCase):
    """As we have only overridden the templates, these tests will check the views
    render without error with our templates but no other functionality will be tested.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()

    def setUp(self):
        self.client = Client()

    def test_password_change_form(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("password_change"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Djangonaut Space")
        self.assertContains(response, "Update password")

    def test_password_change_done(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("password_change_done"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Djangonaut Space")
        self.assertContains(response, "Your password has been updated successfully!")

    def test_password_reset_form(self):
        response = self.client.get(reverse("password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Djangonaut Space")
        self.assertContains(response, "Forgotten your password?")

    def test_password_reset_confirm(self):
        response = self.client.post(
            reverse("password_reset"), {"email": "example@example.com"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        token = response.context[0]["token"]
        uid = response.context[0]["uid"]
        reset_confirm_url = reverse(
            "password_reset_confirm", kwargs={"token": token, "uidb64": uid}
        )
        response = self.client.get(reset_confirm_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Djangonaut Space")
        self.assertContains(response, "Reset password")
        self.assertContains(response, "Change password")

    def test_password_reset_done(self):
        response = self.client.get(reverse("password_reset_done"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Djangonaut Space")
        self.assertContains(
            response,
            "emailed you instructions for setting your password, if an account exists "
            "with the email you entered. You should receive them shortly.",
        )

    def test_password_reset_complete(self):
        response = self.client.get(reverse("password_reset_complete"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Djangonaut Space")
        self.assertContains(
            response, "Your password has been set. You may go ahead and log in now."
        )
