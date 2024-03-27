from __future__ import annotations

from datetime import datetime
from datetime import timezone as dt_timezone

from django.test import Client
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from home.factories import EventFactory


@freeze_time("2012-01-14")
class EventViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @staticmethod
    def create_upcoming_event():
        return EventFactory.create(
            start_time=datetime(2023, 2, 1, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2023, 2, 1, 11, 0, tzinfo=dt_timezone.utc),
        )

    @staticmethod
    def create_past_event():
        return EventFactory.create(
            start_time=datetime(2010, 2, 1, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2010, 2, 1, 11, 0, tzinfo=dt_timezone.utc),
        )

    def test_list_no_events(self):
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/event_list.html")
        self.assertContains(response, "No upcoming events.")
        self.assertContains(response, "No past events.")

    def test_list_upcoming_events_no_past(self):
        upcoming_event = self.create_upcoming_event()
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/event_list.html")
        self.assertNotContains(response, "No upcoming events.")
        self.assertContains(response, "No past events.")
        self.assertContains(response, upcoming_event.title)
        self.assertContains(response, upcoming_event.get_absolute_url())

    def test_list_upcoming_events_and_past(self):
        upcoming_event = self.create_upcoming_event()
        past_event = self.create_past_event()
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/event_list.html")
        self.assertNotContains(response, "No upcoming events.")
        self.assertNotContains(response, "No past events.")
        self.assertContains(response, upcoming_event.title)
        self.assertContains(response, upcoming_event.get_absolute_url())
        self.assertContains(response, past_event.title)
        self.assertContains(response, past_event.get_absolute_url())

    def test_event_detail(self):
        upcoming_event = self.create_upcoming_event()
        timezone.activate("Europe/Berlin")  # UTC + 1
        response = self.client.get(upcoming_event.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/event_detail.html")
        self.assertContains(response, "Feb 01, 2023 11:00 CET")
        self.assertContains(
            response, '<a href="https://zoom.link" rel="nofollow">https://zoom.link</a>'
        )
        timezone.deactivate()
