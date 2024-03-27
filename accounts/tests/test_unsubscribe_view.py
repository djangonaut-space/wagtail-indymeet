from __future__ import annotations

from django.test import Client
from django.test import TestCase
from django.urls import reverse

from accounts.factories import ProfileFactory


class UnsubscribeViewTests(TestCase):
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
        cls.unsubscribe_url = reverse(
            "unsubscribe", kwargs={"user_id": cls.user.id, "token": "dummytoken"}
        )

    def test_user_does_not_exist(self):
        response = self.client.get(
            reverse("unsubscribe", kwargs={"user_id": 500, "token": "dummytoken"})
        )
        self.assertEqual(response.status_code, 404)

    def test_redirect_when_unauthenticated(self):
        response = self.client.get(self.unsubscribe_url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.unsubscribe_url}"
        )

    def test_unsubscribe(self):
        self.client.force_login(self.user)
        response = self.client.get(self.unsubscribe_url)
        self.assertEqual(response.status_code, 200)
        profile = self.user.profile
        profile.refresh_from_db()
        self.assertFalse(profile.receiving_newsletter)
        self.assertFalse(profile.receiving_program_updates)
        self.assertFalse(profile.receiving_event_updates)
