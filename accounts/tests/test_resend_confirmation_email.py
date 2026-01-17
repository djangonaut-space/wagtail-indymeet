from django.core import mail
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from accounts.factories import UserFactory


class ResendConfirmationEmailViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.resend_confirmation_email_url = reverse("resend_email_confirmation")

    def test_must_be_authentication(self):
        response = self.client.post(self.resend_confirmation_email_url, {}, follow=True)
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.resend_confirmation_email_url}",
        )

    def test_get_update_email_subscription_url(self):
        self.client.force_login(self.user)
        response = self.client.post(self.resend_confirmation_email_url, {}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile Info")
        self.assertContains(response, "A verification email has been sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Verify your email - Djangonaut Space")
        self.assertIn(
            "Thank you for signing up to Djangonaut Space! Click the link to verify your email:",
            mail.outbox[0].body,
        )
