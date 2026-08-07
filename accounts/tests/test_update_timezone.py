from django.test import Client
from django.test import TestCase
from django.urls import reverse

from accounts.factories import UserFactory
from tests.timezones import CENTRAL_EUROPEAN_TIMEZONE
from tests.timezones import US_EASTERN_TIMEZONE


class UpdateTimezoneViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.update_timezone_url = reverse("update_timezone")

    def test_must_be_authenticated(self):
        response = self.client.post(
            self.update_timezone_url, {"timezone": US_EASTERN_TIMEZONE}
        )
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.update_timezone_url}",
        )

    def test_saves_valid_timezone(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.update_timezone_url, {"timezone": US_EASTERN_TIMEZONE}
        )
        self.assertEqual(response.status_code, 204)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.timezone, US_EASTERN_TIMEZONE)

    def test_updates_existing_timezone(self):
        self.client.force_login(self.user)
        self.user.profile.timezone = US_EASTERN_TIMEZONE
        self.user.profile.save(update_fields=["timezone"])

        response = self.client.post(
            self.update_timezone_url, {"timezone": CENTRAL_EUROPEAN_TIMEZONE}
        )
        self.assertEqual(response.status_code, 204)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.timezone, CENTRAL_EUROPEAN_TIMEZONE)

    def test_rejects_invalid_timezone(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.update_timezone_url, {"timezone": "Not/A_Timezone"}
        )
        self.assertEqual(response.status_code, 400)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.timezone, "")

    def test_rejects_missing_timezone(self):
        self.client.force_login(self.user)
        response = self.client.post(self.update_timezone_url, {})
        self.assertEqual(response.status_code, 400)
