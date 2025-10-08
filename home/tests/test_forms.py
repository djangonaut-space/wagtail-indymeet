from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.factories import UserFactory
from home.factories import QuestionFactory, SessionFactory
from home.factories import SurveyFactory
from home.factories import UserSurveyResponseFactory
from home.forms import CreateUserSurveyResponseForm
from home.forms import EditUserSurveyResponseForm
from home.models import TypeField
from home.models import UserQuestionResponse
from home.models import UserSurveyResponse


class UserSurveyResponseFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.simple_survey = SurveyFactory()
        cls.simple_survey_question = QuestionFactory.create(
            survey=cls.simple_survey,
            label=f"Simple question?",
            type_field="text",
        )
        # Create a full survey with all the bells and whistles
        cls.survey = SurveyFactory.create()
        cls.user = UserFactory.create()
        extra_type_field_kwargs = {
            "RATING": {"choices": "4"},
            "RADIO": {"choices": "Yes, No"},
            "MULTI_SELECT": {"choices": "Mon, Tue, Wed, Thur, Fri, Sat, Sun"},
            "SELECT": {"choices": "django, django-cms, django-crispy-forms"},
        }
        cls.question_ids = {}
        for type_field in TypeField.values:
            extra_kwargs = extra_type_field_kwargs.get(type_field, {})
            question = QuestionFactory.create(
                survey=cls.survey,
                label=f"{type_field} question?",
                type_field=type_field,
                **extra_kwargs,
            )
            cls.question_ids[type_field] = question.id

    def test_initialize_form(self):
        form = CreateUserSurveyResponseForm(survey=self.survey, user=self.user)
        self.assertEqual(
            set(form.field_names),
            {f"field_survey_{value}" for value in self.question_ids.values()},
        )

    def test_rating_validator_cannot_be_less_than_1(self):
        rating_field_name = f"field_survey_{self.question_ids['RATING']}"
        form = CreateUserSurveyResponseForm(
            survey=self.survey,
            user=self.user,
            data={rating_field_name: "0"},
        )
        self.assertFalse(form.is_valid())
        self.assertIn(rating_field_name, form.errors)
        self.assertEqual(
            form.errors[rating_field_name], ["Value cannot be less than 1."]
        )

    def test_rating_validator_must_be_number(self):
        rating_field_name = f"field_survey_{self.question_ids['RATING']}"
        form = CreateUserSurveyResponseForm(
            survey=self.survey,
            user=self.user,
            data={rating_field_name: "H"},
        )
        self.assertFalse(form.is_valid())
        self.assertIn(rating_field_name, form.errors)
        self.assertEqual(form.errors[rating_field_name], ["H is not a number."])

    def test_rating_validator_cannot_be_greater_than_max(self):
        rating_field_name = f"field_survey_{self.question_ids['RATING']}"
        form = CreateUserSurveyResponseForm(
            survey=self.survey,
            user=self.user,
            data={rating_field_name: "9"},
        )
        self.assertFalse(form.is_valid())
        self.assertIn(rating_field_name, form.errors)
        self.assertEqual(
            form.errors[rating_field_name],
            ["Value cannot be greater than maximum allowed number of ratings."],
        )

    def test_save_fields_required(self):
        form = CreateUserSurveyResponseForm(
            survey=self.survey,
            user=self.user,
            data={},
        )
        self.assertFalse(form.is_valid())
        for value in self.question_ids.values():
            self.assertIn(f"field_survey_{value}", form.errors)
            self.assertEqual(
                form.errors[f"field_survey_{value}"], ["This field is required."]
            )

    def test_save_valid(self):
        form = CreateUserSurveyResponseForm(
            survey=self.survey,
            user=self.user,
            data={
                f"field_survey_{self.question_ids['RADIO']}": "yes",
                f"field_survey_{self.question_ids['RATING']}": "2",
                f"field_survey_{self.question_ids['MULTI_SELECT']}": [
                    "mon",
                    "tue",
                    "wed",
                ],
                f"field_survey_{self.question_ids['SELECT']}": "django",
                f"field_survey_{self.question_ids['URL']}": "www.example.com",
                f"field_survey_{self.question_ids['EMAIL']}": "hello@world.com",
                f"field_survey_{self.question_ids['NUMBER']}": "1992",
                f"field_survey_{self.question_ids['TEXT']}": "Hello I am some text.",
                f"field_survey_{self.question_ids['TEXT_AREA']}": (
                    "Hello I am some text."
                    " I also must be at least 100 characters."
                    " How crazy!! So I am padding this out as much as possible"
                ),
                f"field_survey_{self.question_ids['DATE']}": "2023-01-02",
            },
        )
        self.assertTrue(form.is_valid())

        form.save()

        user_response = UserSurveyResponse.objects.get(
            user=self.user, survey=self.survey
        )
        self.assertEqual(UserSurveyResponse.objects.count(), 1)
        question_responses = UserQuestionResponse.objects.filter(
            user_survey_response=user_response
        )
        self.assertEqual(question_responses.count(), 10)
        self.assertEqual(
            question_responses.get(question=self.question_ids["RADIO"]).value, "yes"
        )
        self.assertEqual(
            question_responses.get(question=self.question_ids["RATING"]).value, "2"
        )
        self.assertEqual(
            question_responses.get(question=self.question_ids["MULTI_SELECT"]).value,
            "mon,tue,wed",
        )
        self.assertEqual(
            question_responses.get(question=self.question_ids["SELECT"]).value, "django"
        )
        self.assertEqual(
            question_responses.get(question=self.question_ids["URL"]).value,
            "https://www.example.com",
        )
        self.assertEqual(
            question_responses.get(question=self.question_ids["EMAIL"]).value,
            "hello@world.com",
        )
        self.assertEqual(
            question_responses.get(question=self.question_ids["NUMBER"]).value, "1992"
        )
        self.assertEqual(
            question_responses.get(question=self.question_ids["TEXT"]).value,
            "Hello I am some text.",
        )
        self.assertEqual(
            question_responses.get(question=self.question_ids["TEXT_AREA"]).value,
            (
                "Hello I am some text."
                " I also must be at least 100 characters. How crazy!!"
                " So I am padding this out as much as possible"
            ),
        )
        self.assertEqual(
            question_responses.get(question=self.question_ids["DATE"]).value,
            "2023-01-02",
        )

    def test_save_duplicate_response_raises_non_field_error(self):
        """Test that attempting to save a duplicate response adds a non-field error."""
        # Create initial response
        UserSurveyResponseFactory.create(survey=self.simple_survey, user=self.user)
        # Attempt to create another response for the same user and survey
        form = CreateUserSurveyResponseForm(
            survey=self.simple_survey,
            user=self.user,
            data={
                f"field_survey_{self.simple_survey_question.id}": "Yup",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)
        self.assertIn(
            "You have already submitted a response. Please edit the other instead.",
            form.errors["__all__"],
        )


class EditUserSurveyResponseFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.simple_survey = SurveyFactory()
        cls.simple_survey_question = QuestionFactory.create(
            survey=cls.simple_survey,
            label=f"Simple question?",
            type_field="text",
        )
        cls.user_survey_response = UserSurveyResponseFactory.create(
            survey=cls.simple_survey, user=cls.user
        )

    def test_edit_form(self):
        """Test that attempting to edit a non-editable response adds a non-field error."""
        # Create a session with active application period
        now = timezone.now().date()
        SessionFactory.create(
            application_survey=self.simple_survey,
            application_start_date=now - timedelta(days=1),
            application_end_date=now + timedelta(days=10),
        )
        form = EditUserSurveyResponseForm(
            instance=self.user_survey_response,
            data={
                f"field_survey_{self.simple_survey_question.id}": "Yup",
            },
        )
        self.assertTrue(form.is_valid())
        user_survey_response = form.save()
        self.assertEqual(
            user_survey_response.userquestionresponse_set.get().value, "Yup"
        )

    def test_edit_non_editable_response_raises_non_field_error(self):
        """Test that attempting to edit a non-editable response adds a non-field error."""
        form = EditUserSurveyResponseForm(
            instance=self.user_survey_response,
            data={
                f"field_survey_{self.simple_survey_question.id}": "Yup",
            },
        )
        self.assertFalse(form.is_valid())

        # Check that non-field error was added
        self.assertIn("__all__", form.errors)
        self.assertEqual(
            form.errors["__all__"],
            ["You are no longer able to edit this."],
        )
