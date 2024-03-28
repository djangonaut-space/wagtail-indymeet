from __future__ import annotations

from unittest.mock import patch

from django.core import mail
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser


class SignUpViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("signup")

    def test_signup_template_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration")

    @patch("captcha.fields.ReCaptchaField.validate", return_value=True)
    def test_signup_template_post_success(self, mock_captcha):
        response = self.client.post(
            self.url,
            data={
                "username": "janedoe",
                "email": "jane@whoareyou.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password1": "secretpassword123",
                "password2": "secretpassword123",
                "email_consent": True,
                "accepted_coc": True,
                "receive_newsletter": True,
                "receive_program_updates": True,
                "receive_event_updates": True,
                "g-recaptcha-response": "dummy-response",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration")
        self.assertContains(
            response,
            (
                "Your registration was successful."
                " Please check your email provided for a confirmation link."
            ),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject, "Djangonaut Space Registration Confirmation"
        )
        self.assertIn(
            "Thank you for signing up to Djangonaut Space! Click the link to verify your email:",
            mail.outbox[0].body,
        )
        created_user = CustomUser.objects.get(username="janedoe")
        self.assertTrue(created_user.is_active)
        self.assertTrue(created_user.profile.accepted_coc)
        self.assertTrue(created_user.profile.receiving_newsletter)
        self.assertTrue(created_user.profile.receiving_program_updates)
        self.assertTrue(created_user.profile.receiving_event_updates)
