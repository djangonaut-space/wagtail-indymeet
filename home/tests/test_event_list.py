from datetime import datetime, timezone

from django.test import Client, TestCase
from django.urls import reverse
from freezegun import freeze_time

from home.models import Event


@freeze_time("2012-01-14")
class EventListViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @staticmethod
    def create_upcoming_event():
        return Event.objects.create(
            title="Testathon 5.0",
            slug="testathon-5",
            start_time=datetime(2023, 2, 1, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2023, 2, 1, 11, 0, tzinfo=timezone.utc),
            location="zoom",
            status=Event.SCHEDULED,
        )

    @staticmethod
    def create_past_event():
        return Event.objects.create(
            title="Coffee Chat",
            slug="coffee-chat",
            start_time=datetime(2010, 2, 1, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2010, 2, 1, 11, 0, tzinfo=timezone.utc),
            location="zoom",
            status=Event.SCHEDULED,
        )

    def test_no_events(self):
        url = reverse("event_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/event_list.html")
        self.assertContains(response, "No upcoming events.")
        self.assertContains(response, "No past events.")

    def test_upcoming_events_no_past(self):
        upcoming_event = self.create_upcoming_event()
        url = reverse("event_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/event_list.html")
        self.assertNotContains(response, "No upcoming events.")
        self.assertContains(response, "No past events.")
        self.assertContains(response, upcoming_event.title)
        self.assertContains(response, upcoming_event.get_absolute_url())

    def test_upcoming_events_and_past(self):
        upcoming_event = self.create_upcoming_event()
        past_event = self.create_past_event()
        url = reverse("event_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/event_list.html")
        self.assertNotContains(response, "No upcoming events.")
        self.assertNotContains(response, "No past events.")
        self.assertContains(response, upcoming_event.title)
        self.assertContains(response, upcoming_event.get_absolute_url())
        self.assertContains(response, past_event.title)
        self.assertContains(response, past_event.get_absolute_url())
