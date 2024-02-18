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
