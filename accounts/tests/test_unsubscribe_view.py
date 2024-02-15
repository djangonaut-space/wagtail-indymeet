from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser


class UnsubscribeViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(username='test', email='example@example.com', password='')
        cls.user.refresh_from_db()
        cls.user.profile.receiving_newsletter = True
        cls.user.profile.receiving_program_updates = True
        cls.user.profile.receiving_event_updates = True
        cls.user.profile.save()
        cls.unsubscribe_url = reverse("unsubscribe", kwargs={"user_id": cls.user.id, "token": "dummytoken"})

    def test_user_does_not_exist(self):
        response = self.client.get(reverse("unsubscribe", kwargs={"user_id": 500, "token": "dummytoken"}))
        self.assertEqual(response.status_code, 404)

    def test_redirect_when_unauthenticated(self):
        response = self.client.get(self.unsubscribe_url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.unsubscribe_url}")

    def test_unsubscribe(self):
        self.client.force_login(self.user)
        response = self.client.get(self.unsubscribe_url)
        self.assertEqual(response.status_code, 200)
        profile = self.user.profile
        profile.refresh_from_db()
        self.assertFalse(profile.receiving_newsletter)
        self.assertFalse(profile.receiving_program_updates)
        self.assertFalse(profile.receiving_event_updates)
