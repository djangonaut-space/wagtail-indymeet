from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.factories import UserFactory
from home.factories import (
    QuestionFactory,
    SessionFactory,
    SurveyFactory,
    UserQuestionResponseFactory,
    UserSurveyResponseFactory,
)
from home.models import UserQuestionResponse, UserSurveyResponse


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

    def test_cannot_access_survey_before_application_opens(self):
        """Test users cannot access survey form before application period starts."""
        now = timezone.now().date()
        SessionFactory.create(
            application_survey=self.survey,
            application_start_date=now + timedelta(days=5),
            application_end_date=now + timedelta(days=15),
        )
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "will be open on")
        self.assertNotContains(response, "Submit")

    def test_cannot_access_survey_after_application_closes(self):
        """Users should not be able to access the survey form after the application period ends."""
        now = timezone.now().date()
        SessionFactory.create(
            application_survey=self.survey,
            application_start_date=now - timedelta(days=15),
            application_end_date=now - timedelta(days=5),
        )
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "application is closed")
        self.assertNotContains(response, "Submit")

    def test_login_required(self):
        response = self.client.get(self.url, follow=True)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_email_confirmed_required(self):
        self.user.profile.email_confirmed = False
        self.user.profile.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url, follow=True)
        self.assertRedirects(response, reverse("profile"))
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            str(messages[0]),
            "Please confirm your email address before submitting a survey response.",
        )
        self.assertEqual(messages[0].level_tag, "warning")

    def test_only_one_per_user(self):
        self.client.force_login(self.user)
        UserSurveyResponseFactory(survey=self.survey, user=self.user)
        response = self.client.get(self.url, follow=True)
        self.assertRedirects(response, reverse("session_list"))
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            str(messages[0]), "You have already submitted a response to this survey."
        )
        self.assertEqual(messages[0].level_tag, "warning")

    def test_success_get(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, "Test Survey")
        self.assertContains(response, "This is a description of the survey!")

    def test_template_shows_create_mode(self):
        """Test that template renders correctly in create mode."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        # Should show "Create" in breadcrumb
        self.assertIn(">Create</li>", content)
        # Should NOT show "Edit" in breadcrumb
        self.assertNotIn(">Edit</li>", content)
        # In create mode, the breadcrumb should show survey name as plain text, not a link
        self.assertNotIn(
            f'<a href="{reverse("user_survey_response", kwargs={"slug": self.survey.slug})}"',
            content,
        )

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

        self.assertContains(response, "Survey successfully saved!")
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
        cls.url = reverse("user_survey_response", kwargs={"slug": cls.survey.slug})

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
        self.assertEqual(response.status_code, 404)


class EditUserSurveyResponseViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.survey = SurveyFactory.create(
            name="Test Survey",
            description="This is a description of the survey!",
        )
        cls.user = UserFactory.create()
        cls.question = QuestionFactory.create(
            survey=cls.survey,
            label="How are you?",
        )
        cls.survey_response = UserSurveyResponseFactory(
            survey=cls.survey, user=cls.user
        )
        UserQuestionResponseFactory(
            user_survey_response=cls.survey_response,
            question=cls.question,
            value="Good",
        )
        cls.url = reverse("edit_user_survey_response", kwargs={"slug": cls.survey.slug})

    def test_login_required(self):
        response = self.client.get(self.url, follow=True)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_cannot_edit_others_survey_response(self):
        different_user = UserFactory.create()
        self.client.force_login(different_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_can_edit_survey_response(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Survey")
        self.assertContains(response, "How are you?")
        self.assertContains(response, "Good")

    def test_template_shows_edit_mode(self):
        """Test that template renders correctly in edit mode."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        # Should show "Edit" in breadcrumb
        self.assertIn(">Edit</li>", content)
        # Should NOT show "Create" in breadcrumb
        self.assertNotIn(">Create</li>", content)
        # Should have link back to survey response view in breadcrumb
        self.assertIn(
            f'href="{reverse("user_survey_response", kwargs={"slug": self.survey.slug})}"',
            content,
        )

    def test_edit_survey_response_success(self):
        # Create a session with active application period
        SessionFactory.create_active(self.survey)
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data={
                f"field_survey_{self.question.id}": "Excellent",
                "github_username": "testuser",
            },
            follow=True,
        )
        self.assertContains(response, "Survey successfully updated!")
        self.assertRedirects(response, reverse("profile"))
        updated_response = UserQuestionResponse.objects.get(
            user_survey_response=self.survey_response, question=self.question
        )
        self.assertEqual(updated_response.value, "Excellent")

    def test_cannot_edit_session_application_after_deadline(self):
        # Create a session with past application deadline
        now = timezone.now().date()
        SessionFactory.create(
            application_survey=self.survey,
            application_start_date=now - timedelta(days=10),
            application_end_date=now - timedelta(days=2),
        )
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data={f"field_survey_{self.question.id}": "Excellent"},
            follow=True,
        )
        self.assertContains(response, "This application is closed.")

    def test_can_edit_session_application_within_deadline(self):
        # Create a session with active application period
        SessionFactory.create_active(self.survey)
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data={f"field_survey_{self.question.id}": "Excellent"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Survey")
