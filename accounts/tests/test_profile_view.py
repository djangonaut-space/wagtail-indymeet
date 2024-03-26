from django.test import Client, TestCase
from django.urls import reverse

from accounts.factories import ProfileFactory


class ProfileViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @classmethod
    def setUpTestData(cls):
        profile = ProfileFactory.create(user__username="test")
        cls.user = profile.user
        cls.profile_url = reverse("profile")
        cls.update_profile_url = reverse("update_user")

    def test_redirect_when_unauthenticated(self):
        response = self.client.get(self.profile_url, follow=True)
        self.assertRedirects(response, f"{reverse('login')}?next={self.profile_url}")

    def test_profile(self):
        self.client.force_login(self.user)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome, Jane")
        self.assertContains(response, "Profile Info")
        self.assertContains(response, "test")
        self.assertContains(response, "Jane Doe")

    def test_update_profile_initial_data(self):
        self.client.force_login(self.user)
        response = self.client.get(self.update_profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Update Profile Info")
        self.assertContains(response, "test")
        self.assertContains(response, "Jane")
        self.assertContains(response, "Doe")
        self.assertContains(response, "You have not confirmed your email address.")

    def test_update_profile(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.update_profile_url,
            data={
                "username": "janedoe",
                "email": "jane@newemail.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "receive_newsletter": True,
                "receive_program_updates": True,
                "receive_event_updates": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile Info")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.receiving_newsletter, True)
