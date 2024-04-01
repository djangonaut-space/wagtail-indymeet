from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from accounts.factories import UserFactory
from home.factories import QuestionFactory
from home.factories import SurveyFactory
from home.factories import UserQuestionResponseFactory
from home.factories import UserSurveyResponseFactory
from home.models import UserQuestionResponse
from home.models import UserSurveyResponse


class CreateUserSurveyResponseFormViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.survey = SurveyFactory.create(
            name="Test Survey", description="This is a description of the survey!"
        )
        cls.url = reverse("survey_response_create", kwargs={"slug": cls.survey.slug})
        cls.user = UserFactory.create(profile__email_confirmed=True)
        cls.question = QuestionFactory.create(
            survey=cls.survey,
            label="How are you?",
        )

    def test_login_required(self):
        response = self.client.get(self.url, follow=True)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_email_confirmed_required(self):
        self.user.profile.email_confirmed = False
        self.user.profile.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_only_one_per_user(self):
        self.client.force_login(self.user)
        UserSurveyResponseFactory(survey=self.survey, user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_success_get(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, "Test Survey")
        self.assertContains(response, "This is a description of the survey!")

    def test_error_message(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {})
        self.assertContains(response, "Something went wrong.")
        self.assertEqual(UserSurveyResponse.objects.count(), 0)

    def test_success_message(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data={f"field_survey_{self.question.id}": "Amazing"},
            follow=True,
        )

        self.assertContains(response, "Response sent!")
        self.assertRedirects(response, reverse("session_list"))
        user_response = UserSurveyResponse.objects.get(
            user=self.user, survey=self.survey
        )
        self.assertEqual(
            UserQuestionResponse.objects.get(
                user_survey_response=user_response, question=self.question
            ).value,
            "Amazing",
        )


class UserSurveyResponseViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.survey = SurveyFactory.create(
            name="Test Survey", description="This is a description of the survey!"
        )
        cls.user = UserFactory.create()
        cls.question_1 = QuestionFactory.create(
            survey=cls.survey,
            label="How are you?",
        )
        cls.question_2 = QuestionFactory.create(
            survey=cls.survey,
            label="What is your favourite food?",
        )
        cls.survey_response = UserSurveyResponseFactory(
            survey=cls.survey, user=cls.user
        )
        UserQuestionResponseFactory(
            user_survey_response=cls.survey_response,
            question=cls.question_1,
            value="Very good",
        )
        UserQuestionResponseFactory(
            user_survey_response=cls.survey_response,
            question=cls.question_2,
            value="Pizza",
        )
        cls.url = reverse("user_survey_response", kwargs={"pk": cls.survey_response.id})

    def test_success_get(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Survey")
        self.assertContains(response, "This is a description of the survey!")
        self.assertContains(response, "How are you?")
        self.assertContains(response, "Very good")
        self.assertContains(response, "What is your favourite food?")
        self.assertContains(response, "Pizza")
        self.assertNotContains(response, "Submit")

    def test_cannot_view_others_survey_response(self):
        different_user = UserFactory.create()
        self.client.force_login(different_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
