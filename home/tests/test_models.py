from datetime import datetime

from django.test import TestCase
from freezegun import freeze_time

from home.models import Session


class SessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = Session.objects.create(
            start_date=datetime(2024, 1, 15),
            end_date=datetime(2024, 3, 11),
            title="2024 Session 1",
            slug="2024-session-1",
            invitation_date=datetime(2023, 12, 1),
            application_start_date=datetime(2023, 10, 16),
            application_end_date=datetime(2023, 11, 15),
        )

    def test_is_accepting_applications(self):
        with freeze_time("2023-10-15"):
            self.assertFalse(self.session.is_accepting_applications())

        with freeze_time("2023-10-16"):
            self.assertTrue(self.session.is_accepting_applications())

        with freeze_time("2023-11-15"):
            self.assertTrue(self.session.is_accepting_applications())

        with freeze_time("2023-11-16"):
            self.assertFalse(self.session.is_accepting_applications())
