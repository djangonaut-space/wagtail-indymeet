from __future__ import annotations

from datetime import datetime

from django.test import Client
from django.test import TestCase
from django.urls import reverse
from freezegun import freeze_time

from accounts.factories import UserFactory
from home.factories import SessionFactory
from home.factories import SurveyFactory
from home.factories import UserSurveyResponseFactory


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
        cls.survey = SurveyFactory.create(name="Application Survey")
        cls.session_application_open_with_survey = SessionFactory.create(
            application_start_date=datetime(2023, 10, 16).date(),
            application_end_date=datetime(2023, 11, 15).date(),
            application_url=None,
            application_survey=cls.survey,
        )
        cls.survey_url = reverse(
            "survey_response_create", kwargs={"slug": cls.survey.slug}
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
        self.assertNotContains(response, self.survey_url)
        self.assertNotContains(
            response, self.session_application_closed.application_url
        )
        self.assertNotContains(response, "Your email is not confirmed!")
        self.assertNotContains(response, "You may not be able to apply for sessions")

    def test_session_list_email_not_confirmed(self):
        user = UserFactory.create(profile__email_confirmed=False)
        self.client.force_login(user)
        response = self.client.get(reverse("session_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/session_list.html")
        self.assertContains(response, self.session_application_open.application_url)
        self.assertNotContains(response, self.survey_url)
        self.assertNotContains(
            response, self.session_application_closed.application_url
        )
        self.assertContains(response, "Your email is not confirmed!")
        self.assertContains(response, "You may not be able to apply for sessions")

    def test_session_list_email_confirmed(self):
        user = UserFactory.create(profile__email_confirmed=True)
        self.client.force_login(user)
        response = self.client.get(reverse("session_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/session_list.html")
        self.assertContains(response, self.session_application_open.application_url)
        self.assertContains(response, self.survey_url)
        self.assertNotContains(
            response, self.session_application_closed.application_url
        )
        self.assertNotContains(response, "Your email is not confirmed!")
        self.assertNotContains(response, "You may not be able to apply for sessions")

    def test_session_list_email_confirmed_already_applied(self):
        user = UserFactory.create(profile__email_confirmed=True)
        UserSurveyResponseFactory(survey=self.survey, user=user)
        self.client.force_login(user)
        response = self.client.get(reverse("session_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/session_list.html")
        self.assertContains(response, self.session_application_open.application_url)
        self.assertNotContains(response, self.survey_url)
        self.assertNotContains(
            response, self.session_application_closed.application_url
        )
        self.assertNotContains(response, "Your email is not confirmed!")
        self.assertNotContains(response, "You may not be able to apply for sessions")

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
        self.assertNotContains(response, "Your email is not confirmed!")
        self.assertNotContains(response, "You may not be able to apply for sessions")

    def test_session_detail_open_application_with_survey_email_not_confirmed(self):
        user = UserFactory.create(profile__email_confirmed=False)
        self.client.force_login(user)
        url = reverse(
            "session_detail",
            kwargs={"slug": self.session_application_open_with_survey.slug},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/session_detail.html")
        self.assertNotContains(response, self.survey_url)
        self.assertIn(
            "You have 11 hours, 59 minutes to submit your application",
            " ".join(
                response.rendered_content.split()
            ),  # Remove the non-breaking spaces
        )
        self.assertContains(response, "Your email is not confirmed!")
        self.assertContains(response, "You may not be able to apply for sessions")

    def test_session_detail_open_application_with_survey_email_confirmed(self):
        user = UserFactory.create(profile__email_confirmed=True)
        self.client.force_login(user)
        url = reverse(
            "session_detail",
            kwargs={"slug": self.session_application_open_with_survey.slug},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/session_detail.html")
        self.assertContains(response, self.survey_url)
        self.assertIn(
            "You have 11 hours, 59 minutes to submit your application",
            " ".join(
                response.rendered_content.split()
            ),  # Remove the non-breaking spaces
        )
        self.assertNotContains(response, "Your email is not confirmed!")
        self.assertNotContains(response, "You may not be able to apply for sessions")

    def test_session_detail_open_application_with_survey_email_confirmed_already_applied(
        self,
    ):
        user = UserFactory.create(profile__email_confirmed=True)
        UserSurveyResponseFactory(survey=self.survey, user=user)
        self.client.force_login(user)
        url = reverse(
            "session_detail",
            kwargs={"slug": self.session_application_open_with_survey.slug},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/prerelease/session_detail.html")
        self.assertNotContains(response, self.survey_url)
        self.assertNotIn(
            "You have 11 hours, 59 minutes to submit your application",
            " ".join(
                response.rendered_content.split()
            ),  # Remove the non-breaking spaces
        )
        self.assertNotContains(response, "Your email is not confirmed!")
        self.assertNotContains(response, "You may not be able to apply for sessions")

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
