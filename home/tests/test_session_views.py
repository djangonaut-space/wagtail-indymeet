from datetime import datetime

from django.test import Client, TestCase
from django.urls import reverse
from freezegun import freeze_time

from home.factories import SessionFactory


@freeze_time("2023-11-16")
class SessionViewTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.session_application_open = SessionFactory.create(
            application_start_date=datetime(2023, 10, 16).date(),
            application_end_date=datetime(2023, 11, 15).date(),
        )
        cls.session_application_closed = SessionFactory.create(
            invitation_date=datetime(2023, 6, 30).date(),
            application_start_date=datetime(2023, 6, 1).date(),
            application_end_date=datetime(2023, 6, 20).date(),
        )

    def test_session_list(self):
        response = self.client.get(reverse("session_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/session_list.html")
        self.assertContains(response, self.session_application_open.application_url)
        self.assertNotContains(
            response, self.session_application_closed.application_url
        )

    def test_session_detail_open_application(self):
        url = reverse(
            "session_detail", kwargs={"slug": self.session_application_open.slug}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/session_detail.html")
        self.assertContains(response, self.session_application_open.application_url)
        self.assertIn(
            "You have 11 hours, 59 minutes to submit your application",
            " ".join(
                response.rendered_content.split()
            ),  # Remove the non-breaking spaces
        )

    def test_session_detail_closed_application(self):
        url = reverse(
            "session_detail", kwargs={"slug": self.session_application_closed.slug}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/session_detail.html")
        self.assertNotContains(
            response, self.session_application_closed.application_url
        )
