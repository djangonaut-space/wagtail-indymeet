from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser


class ProfileViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(
            username="test",
            email="example@example.com",
            password="",
            first_name="Jane",
            last_name="Doe",
        )
        cls.user.refresh_from_db()
        cls.user.profile.receiving_newsletter = True
        cls.user.profile.receiving_program_updates = True
        cls.user.profile.receiving_event_updates = True
        cls.user.profile.save()
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
