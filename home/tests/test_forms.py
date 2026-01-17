import csv
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from accounts.factories import UserFactory
from home.factories import QuestionFactory, SessionFactory
from home.factories import SurveyFactory
from home.factories import UserSurveyResponseFactory
from home.forms import CreateUserSurveyResponseForm
from home.forms import EditUserSurveyResponseForm
from home.forms import SurveyCSVExportForm, SurveyCSVImportForm
from home.models import Question
from home.models import Survey
from home.models import TypeField
from home.models import UserQuestionResponse
from home.models import UserSurveyResponse

User = get_user_model()


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
        SessionFactory.create_active(self.simple_survey)
        form = EditUserSurveyResponseForm(
            instance=self.user_survey_response,
            data={
                f"field_survey_{self.simple_survey_question.id}": "Yup",
                "github_username": "testuser",
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

    def test_edit_form_updates_timestamp(self):
        """Test that editing a survey response updates the updated_at timestamp."""
        # Create a session with active application period
        SessionFactory.create_active(self.simple_survey)

        # Get the original timestamp
        original_timestamp = self.user_survey_response.updated_at

        # Edit the response
        form = EditUserSurveyResponseForm(
            instance=self.user_survey_response,
            data={
                f"field_survey_{self.simple_survey_question.id}": "Updated response",
                "github_username": "testuser",
            },
        )
        self.assertTrue(form.is_valid())
        form.save()

        # Refresh from database
        self.user_survey_response.refresh_from_db()

        # Verify timestamp was updated
        self.assertGreater(
            self.user_survey_response.updated_at,
            original_timestamp,
            "updated_at timestamp should be updated after editing",
        )


class SurveyCSVExportFormTests(TestCase):
    """Test the SurveyCSVExportForm CSV generation methods."""

    @classmethod
    def setUpTestData(cls):
        cls.respondent1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            first_name="John",
            last_name="Doe",
        )
        cls.respondent2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            first_name="Jane",
            last_name="Smith",
        )

        cls.survey = SurveyFactory.create(name="Test Survey")

        cls.question1 = Question.objects.create(
            survey=cls.survey,
            label="What is your email?",
            type_field=TypeField.EMAIL,
            ordering=1,
        )
        cls.question2 = Question.objects.create(
            survey=cls.survey,
            label="Rate your experience",
            type_field=TypeField.RATING,
            choices="5",
            ordering=2,
        )
        cls.question3 = Question.objects.create(
            survey=cls.survey,
            label="Tell us about yourself",
            type_field=TypeField.TEXT_AREA,
            ordering=3,
        )

        # Create survey responses
        cls.response1 = UserSurveyResponse.objects.create(
            survey=cls.survey,
            user=cls.respondent1,
        )
        UserQuestionResponse.objects.create(
            question=cls.question1,
            user_survey_response=cls.response1,
            value="john@example.com",
        )
        UserQuestionResponse.objects.create(
            question=cls.question2,
            user_survey_response=cls.response1,
            value="5",
        )
        UserQuestionResponse.objects.create(
            question=cls.question3,
            user_survey_response=cls.response1,
            value="I am a Django developer with 5 years of experience.",
        )

        cls.response2 = UserSurveyResponse.objects.create(
            survey=cls.survey,
            user=cls.respondent2,
        )
        UserQuestionResponse.objects.create(
            question=cls.question1,
            user_survey_response=cls.response2,
            value="jane@example.com",
        )
        UserQuestionResponse.objects.create(
            question=cls.question2,
            user_survey_response=cls.response2,
            value="4",
        )
        UserQuestionResponse.objects.create(
            question=cls.question3,
            user_survey_response=cls.response2,
            value="I am interested in contributing to open source.",
        )

    def test_clean_scorer_names_parses_correctly(self):
        """Test scorer names are parsed from textarea."""
        form = SurveyCSVExportForm(data={"scorer_names": "Alice\nBob\nCharlie"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["scorer_names"], ["Alice", "Bob", "Charlie"])

    def test_clean_scorer_names_handles_empty_lines(self):
        """Test empty lines are filtered out."""
        form = SurveyCSVExportForm(data={"scorer_names": "Alice\n\nBob\n\n\nCharlie\n"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["scorer_names"], ["Alice", "Bob", "Charlie"])

    def test_clean_scorer_names_handles_empty_string(self):
        """Test empty string returns empty list."""
        form = SurveyCSVExportForm(data={"scorer_names": ""})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["scorer_names"], [])

    def test_generate_full_csv_without_scorers(self):
        """Test full CSV generation without scorer names."""
        form = SurveyCSVExportForm(data={"scorer_names": ""})
        self.assertTrue(form.is_valid())

        response = form.generate_full_csv(self.survey)

        # Parse CSV content (remove BOM if present)
        content = response.content.decode("utf-8-sig")
        csv_reader = csv.reader(io.StringIO(content))
        rows = list(csv_reader)

        # Check header
        expected_header = [
            "Response ID",
            "Submitter Name",
            "What is your email?",
            "Rate your experience",
            "Tell us about yourself",
            "Score",
            "Selection Rank",
        ]
        self.assertEqual(rows[0], expected_header)

        # Check data rows
        self.assertEqual(len(rows), 3)  # Header + 2 responses
        self.assertEqual(rows[1][0], str(self.response1.id))
        self.assertEqual(rows[1][1], "John Doe")
        self.assertEqual(rows[1][5], "")  # Empty Score
        self.assertEqual(rows[1][6], "")  # Empty Selection Rank

    def test_generate_full_csv_with_scorers(self):
        """Test full CSV generation with scorer names."""
        form = SurveyCSVExportForm(data={"scorer_names": "Alice\nBob"})
        self.assertTrue(form.is_valid())

        response = form.generate_full_csv(self.survey)

        # Parse CSV content (remove BOM if present)
        content = response.content.decode("utf-8-sig")
        csv_reader = csv.reader(io.StringIO(content))
        rows = list(csv_reader)

        # Check header includes scorer columns
        expected_header = [
            "Response ID",
            "Submitter Name",
            "What is your email?",
            "Rate your experience",
            "Tell us about yourself",
            "Alice score",
            "Bob score",
            "Score",
            "Selection Rank",
        ]
        self.assertEqual(rows[0], expected_header)
        self.assertEqual(rows[1][5], "")  # Alice score
        self.assertEqual(rows[1][6], "")  # Bob score
        self.assertEqual(rows[1][7], "")  # Score
        self.assertEqual(rows[1][8], "")  # Selection Rank

    def test_generate_single_scorer_csv(self):
        """Test single scorer CSV only includes TEXT_AREA questions."""
        form = SurveyCSVExportForm(data={"scorer_names": ""})
        self.assertTrue(form.is_valid())

        response = form.generate_single_scorer_csv(self.survey)

        # Parse CSV content (remove BOM if present)
        content = response.content.decode("utf-8-sig")
        csv_reader = csv.reader(io.StringIO(content))
        rows = list(csv_reader)

        # Check header - only TEXT_AREA questions and Score/Selection Rank columns
        expected_header = [
            "Response ID",
            "Tell us about yourself",
            "Tell us about yourself Score",
        ]
        self.assertEqual(rows[0], expected_header)

        # Check data rows
        self.assertEqual(len(rows), 3)  # Header + 2 responses
        self.assertEqual(rows[1][0], str(self.response1.id))
        self.assertEqual(
            rows[1][1], "I am a Django developer with 5 years of experience."
        )
        self.assertEqual(rows[1][2], "")

    def test_generate_csv_routes_to_full(self):
        """Test generate_csv method routes to full CSV by default."""
        form = SurveyCSVExportForm(data={"scorer_names": ""})
        self.assertTrue(form.is_valid())

        response = form.generate_csv(self.survey, {})

        # Check filename to verify it's the full CSV
        self.assertIn("_responses.csv", response["Content-Disposition"])

    def test_generate_csv_routes_to_single_scorer(self):
        """Test generate_csv method routes to single scorer CSV when requested."""
        form = SurveyCSVExportForm(data={"scorer_names": ""})
        self.assertTrue(form.is_valid())

        response = form.generate_csv(self.survey, {"generate_scorer_csv": ""})

        # Check filename to verify it's the single scorer CSV
        self.assertIn("_single_scorer.csv", response["Content-Disposition"])

    def test_csv_uses_utf8_encoding(self):
        """Test CSV files use UTF-8 encoding with BOM."""
        form = SurveyCSVExportForm(data={"scorer_names": ""})
        self.assertTrue(form.is_valid())

        response = form.generate_full_csv(self.survey)

        # Check content type
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("utf-8", response["Content-Type"])

        # Check BOM is present
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))


class SurveyCSVImportFormTests(TestCase):
    """Test the CSV import form validation and processing logic."""

    @classmethod
    def setUpTestData(cls):
        cls.survey = SurveyFactory.create(name="Test Survey")
        cls.survey2 = SurveyFactory.create(name="Another Survey")
        cls.user1 = UserFactory.create()
        cls.user2 = UserFactory.create()

        # Create survey responses
        cls.response1 = UserSurveyResponse.objects.create(
            survey=cls.survey,
            user=cls.user1,
        )
        cls.response2 = UserSurveyResponse.objects.create(
            survey=cls.survey,
            user=cls.user2,
        )
        cls.response3 = UserSurveyResponse.objects.create(
            survey=cls.survey2,
            user=cls.user1,
        )

    def test_clean_csv_file_valid_data(self):
        """Test clean_csv_file parses valid CSV correctly."""
        csv_content = (
            "Response ID,Score,Selection Rank\n"
            f"{self.response1.id},10,0\n"
            f"{self.response2.id},8,1\n"
        )
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertTrue(form.is_valid())

        updates = form.cleaned_data["csv_file"]
        self.assertEqual(len(updates), 2)
        self.assertIn((self.response1.id, 10, 0), updates)
        self.assertIn((self.response2.id, 8, 1), updates)

    def test_clean_csv_file_with_extra_columns(self):
        """Test clean_csv_file ignores extra columns."""
        csv_content = (
            "Response ID,Submitter Name,Selection Rank,Question 1,Score,Extra Column\n"
            f"{self.response1.id},John Doe,1,Answer,5,Ignored\n"
        )
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertTrue(form.is_valid())

        updates = form.cleaned_data["csv_file"]
        self.assertEqual(updates, [(self.response1.id, 5, 1)])

    def test_clean_csv_file_skips_empty_rows(self):
        """Test clean_csv_file skips rows with empty Response ID, Score, or Selection Rank."""
        csv_content = (
            "Response ID,Score,Selection Rank\n"
            f"{self.response1.id},10,1\n"
            ",8,1\n"  # Empty Response ID
            f"{self.response2.id},,1\n"  # Empty Score
            f"{self.response3.id},10,\n"  # Empty Selection rank
        )
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertTrue(form.is_valid())

        updates = form.cleaned_data["csv_file"]
        self.assertEqual(updates, [(self.response1.id, 10, 1)])

    def test_clean_csv_file_missing_response_id_column(self):
        """Test clean_csv_file fails if Response ID column is missing."""
        csv_content = "Score,Selection Rank\n10,8\n"
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertFalse(form.is_valid())
        self.assertIn("Response ID", str(form.errors["csv_file"]))

    def test_clean_csv_file_missing_score_column(self):
        """Test clean_csv_file fails if Score column is missing."""
        csv_content = "Response ID,Selection Rank\n1,2\n"
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertFalse(form.is_valid())
        self.assertIn("Score", str(form.errors["csv_file"]))

    def test_clean_csv_file_selection_rank_column(self):
        """Test clean_csv_file fails if Selection Rank column is missing."""
        csv_content = "Response ID,Score\n1,2\n"
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertFalse(form.is_valid())
        self.assertIn("Selection Rank", str(form.errors["csv_file"]))

    def test_clean_csv_file_invalid_response_id(self):
        """Test clean_csv_file shows error for non-integer Response ID."""
        csv_content = "Response ID,Score,Selection Rank\nabc,10,1\n"
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertFalse(form.is_valid())
        self.assertIn("Invalid Response ID", str(form.errors["csv_file"]))

    def test_clean_csv_file_invalid_score(self):
        """Test clean_csv_file shows error for non-integer Score."""
        csv_content = f"Response ID,Score,Selection Rank\n{self.response1.id},abc,1\n"
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertFalse(form.is_valid())
        self.assertIn("Invalid Score", str(form.errors["csv_file"]))

    def test_clean_csv_file_no_valid_rows(self):
        """Test clean_csv_file shows error when no valid data rows."""
        csv_content = "Response ID,Score,Selection Rank\n,,\n,,\n"
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertFalse(form.is_valid())
        self.assertIn("No valid data rows", str(form.errors["csv_file"]))

    def test_clean_csv_file_with_utf8_bom(self):
        """Test clean_csv_file handles UTF-8 BOM correctly."""
        csv_content = (
            "\ufeff"  # UTF-8 BOM
            "Response ID,Score,Selection Rank\n"
            f"{self.response1.id},10,1\n"
        )
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertTrue(form.is_valid())

        updates = form.cleaned_data["csv_file"]
        self.assertEqual(updates, [(self.response1.id, 10, 1)])

    def test_import_scores_valid_data(self):
        """Test import_scores updates scores correctly."""
        csv_content = (
            "Response ID,Score,Selection Rank\n"
            f"{self.response1.id},10,1\n"
            f"{self.response2.id},8,2\n"
        )
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertTrue(form.is_valid())

        result = form.import_scores(self.survey)

        # Verify scores and selection ranks were updated
        self.response1.refresh_from_db()
        self.response2.refresh_from_db()
        self.assertEqual(self.response1.score, 10)
        self.assertEqual(self.response1.selection_rank, 1)
        self.assertEqual(self.response2.score, 8)
        self.assertEqual(self.response2.selection_rank, 2)
        self.assertEqual(result["updated"], 2)

    def test_import_scores_skips_wrong_survey(self):
        """Test import_scores silently skips responses from other surveys."""
        csv_content = (
            "Response ID,Score,Selection Rank\n"
            f"{self.response1.id},10,1\n"
            f"{self.response3.id},5,2\n"  # This belongs to survey2
        )
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertTrue(form.is_valid())

        result = form.import_scores(self.survey)

        # Verify only response1 was updated
        self.response1.refresh_from_db()
        self.response3.refresh_from_db()
        self.assertEqual(self.response1.score, 10)
        self.assertEqual(self.response1.selection_rank, 1)
        self.assertIsNone(self.response3.score)
        self.assertIsNone(self.response3.selection_rank)
        self.assertEqual(result["updated"], 1)

    def test_import_scores_skips_not_found(self):
        """Test import_scores silently skips non-existent response IDs."""
        csv_content = (
            "Response ID,Score,Selection Rank\n"
            f"{self.response1.id},10,1\n"
            "999999,5,2\n"  # Non-existent ID
        )
        csv_file = SimpleUploadedFile(
            "scores.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

        form = SurveyCSVImportForm(data={}, files={"csv_file": csv_file})
        self.assertTrue(form.is_valid())

        result = form.import_scores(self.survey)

        # Verify response1 was updated
        self.response1.refresh_from_db()
        self.assertEqual(self.response1.score, 10)
        self.assertEqual(self.response1.selection_rank, 1)
        self.assertEqual(result["updated"], 1)
