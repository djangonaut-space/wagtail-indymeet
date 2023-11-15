from datetime import datetime

from django.test import TestCase
from freezegun import freeze_time

from home.models import Session


class SessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = Session.objects.create(
            start_date=datetime(2024, 1, 15).date(),
            end_date=datetime(2024, 3, 11).date(),
            title="2024 Session 1",
            slug="2024-session-1",
            invitation_date=datetime(2023, 12, 1).date(),
            application_start_date=datetime(2023, 10, 16).date(),
            application_end_date=datetime(2023, 11, 15).date(),
        )

    def test_is_accepting_applications(self):
        # Ensure that the types of fields are from django, not from when I created the object in memory
        self.session.refresh_from_db()

        with freeze_time("2023-10-15"):
            self.assertFalse(self.session.is_accepting_applications())

        with freeze_time("2023-10-15 12:00:00"):
            # In UTC, so this is the 16th somewhere in the world
            self.assertTrue(self.session.is_accepting_applications())

        with freeze_time("2023-10-16"):
            self.assertTrue(self.session.is_accepting_applications())

        with freeze_time("2023-11-15"):
            self.assertTrue(self.session.is_accepting_applications())

        with freeze_time("2023-11-16"):
            # In UTC, so is the 15th still somewhere in the world
            self.assertTrue(self.session.is_accepting_applications())

        with freeze_time("2023-11-16 12:00:00"):
            # No longer 15th AoE
            self.assertFalse(self.session.is_accepting_applications())
