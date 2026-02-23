from django.test import Client
from django.test import TestCase
from django.urls import reverse

from accounts.factories import ProfileFactory, UserFactory


class UpdateEmailSubscriptionViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @classmethod
    def setUpTestData(cls):
        profile = ProfileFactory.create(
            receiving_newsletter=True,
            receiving_program_updates=True,
            receiving_event_updates=True,
        )
        cls.user = profile.user
        cls.update_email_subscription_url = reverse("email_subscriptions")

    def test_redirect_when_unauthenticated(self):
        response = self.client.get(self.update_email_subscription_url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.update_email_subscription_url}"
        )

    def test_get_update_email_subscription_url(self):
        self.client.force_login(self.user)
        response = self.client.get(self.update_email_subscription_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Update Email Subscriptions")
        self.assertContains(
            response,
            "Please confirm which email updates you would like to be subscribed to.",
        )
        self.assertContains(response, "checked", 3)

    def test_update_email_subscription_unsubscribe(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.update_email_subscription_url,
            data={
                "receiving_newsletter": False,
                "receiving_event_updates": False,
                "receiving_program_updates": False,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile Info")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.receiving_newsletter, False)
        self.assertEqual(self.user.profile.receiving_event_updates, False)
        self.assertEqual(self.user.profile.receiving_program_updates, False)


class UpdateEmailSubscriptionViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @classmethod
    def setUpTestData(cls):
        cls.user = ProfileFactory.create().user
        UserFactory.create(username="newusername", email="new@email.com")
        cls.update_account_url = reverse("update_user")

    def test_cant_reuse_email(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.update_account_url,
            data={
                "username": "janedoe",
                "email": "new@email.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password1": "secretpassword123",
                "password2": "secretpassword123",
                "receive_newsletter": True,
                "receive_program_updates": True,
                "receive_event_updates": True,
            },
            follow=True,
        )
        self.assertContains(
            response,
            "This email has already been used. Please reset your password.",
        )

    def test_cant_reuse_username(self):
        self.client.force_login(self.user)
        self.client.force_login(self.user)
        response = self.client.post(
            self.update_account_url,
            data={
                "username": "newusername",
                "email": "fine@email.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password1": "secretpassword123",
                "password2": "secretpassword123",
                "receive_newsletter": True,
                "receive_program_updates": True,
                "receive_event_updates": True,
            },
            follow=True,
        )
        print(response.text)
        self.assertContains(
            response,
            "A user with that username already exists.",
        )
