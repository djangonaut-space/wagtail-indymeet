from typing import List
from typing import Tuple

from django import forms
from django.core.validators import MaxLengthValidator
from django.core.validators import MinLengthValidator
from django.db import transaction, IntegrityError
from django.utils.translation import gettext_lazy as _

from home.constants import DATE_INPUT_FORMAT
from home.constants import SURVEY_FIELD_VALIDATORS
from home.models import Question
from home.models import TypeField
from home.models import UserQuestionResponse
from home.models import UserSurveyResponse
from home.validators import RatingValidator
from home.widgets import CheckboxSelectMultipleSurvey
from home.widgets import DateSurvey
from home.widgets import RadioSelectSurvey
from home.widgets import RatingSurvey


def make_choices(question: Question) -> list[tuple[str, str]]:
    choices = []
    for choice in question.choices.split(","):
        choice = choice.strip()
        choices.append((choice.replace(" ", "_").lower(), choice))
    return choices


def to_field_name(question: Question) -> str:
    """Convert a question to the response field name key."""
    return f"field_survey_{question.id}"


def get_response_value(data: dict, question: Question) -> str:
    """
    Fetch the question's value from the data dictionary,
    typically a cleaned_data.
    """
    field_name = to_field_name(question)
    return (
        ",".join(data[field_name])
        if question.type_field == TypeField.MULTI_SELECT
        else data[field_name]
    )


class BaseSurveyForm(forms.Form):
    def __init__(self, *args, survey, user, **kwargs):
        self.survey = survey
        self.user = user if user.is_authenticated else None
        self.field_names = []
        self.questions = self.survey.questions.all().order_by("ordering")
        super().__init__(*args, **kwargs)

        for question in self.questions:
            # to generate field name
            field_name = to_field_name(question)

            if question.type_field == TypeField.MULTI_SELECT:
                choices = make_choices(question)
                self.fields[field_name] = forms.MultipleChoiceField(
                    choices=choices,
                    label=question.label,
                    widget=CheckboxSelectMultipleSurvey,
                )
            elif question.type_field == TypeField.RADIO:
                choices = make_choices(question)
                self.fields[field_name] = forms.ChoiceField(
                    choices=choices, label=question.label, widget=RadioSelectSurvey
                )
            elif question.type_field == TypeField.SELECT:
                choices = make_choices(question)
                empty_choice = [("", _("Choose"))]
                choices = empty_choice + choices
                self.fields[field_name] = forms.ChoiceField(
                    choices=choices, label=question.label
                )
            elif question.type_field == TypeField.NUMBER:
                self.fields[field_name] = forms.IntegerField(label=question.label)
            elif question.type_field == TypeField.URL:
                self.fields[field_name] = forms.URLField(
                    label=question.label,
                    validators=[
                        MaxLengthValidator(SURVEY_FIELD_VALIDATORS["max_length"]["url"])
                    ],
                )
            elif question.type_field == TypeField.EMAIL:
                self.fields[field_name] = forms.EmailField(
                    label=question.label,
                    validators=[
                        MaxLengthValidator(
                            SURVEY_FIELD_VALIDATORS["max_length"]["email"]
                        )
                    ],
                )
            elif question.type_field == TypeField.DATE:
                self.fields[field_name] = forms.DateField(
                    label=question.label,
                    widget=DateSurvey(),
                    input_formats=DATE_INPUT_FORMAT,
                )
            elif question.type_field == TypeField.TEXT_AREA:
                self.fields[field_name] = forms.CharField(
                    label=question.label,
                    widget=forms.Textarea,
                    validators=[
                        MinLengthValidator(
                            SURVEY_FIELD_VALIDATORS["min_length"]["text_area"]
                        )
                    ],
                )
            elif question.type_field == TypeField.RATING:
                self.fields[field_name] = forms.CharField(
                    label=question.label,
                    widget=RatingSurvey,
                    validators=[
                        MaxLengthValidator(len(str(int(question.choices)))),
                        RatingValidator(int(question.choices)),
                    ],
                )
                self.fields[field_name].widget.num_ratings = int(question.choices)
            else:
                self.fields[field_name] = forms.CharField(
                    label=question.label,
                    validators=[
                        MinLengthValidator(
                            SURVEY_FIELD_VALIDATORS["min_length"]["text"]
                        ),
                        MaxLengthValidator(
                            SURVEY_FIELD_VALIDATORS["max_length"]["text"]
                        ),
                    ],
                )

            self.fields[field_name].required = question.required
            self.fields[field_name].help_text = question.help_text
            self.field_names.append(field_name)

    def clean(self):
        cleaned_data = super().clean()

        for field_name in self.field_names:
            try:
                field = cleaned_data[field_name]
            except KeyError:
                raise forms.ValidationError("You must enter valid data")

            if self.fields[field_name].required and not field:
                self.add_error(field_name, "This field is required")

        return cleaned_data


class CreateUserSurveyResponseForm(BaseSurveyForm):

    def clean(self):
        cleaned_data = super().clean()
        if UserSurveyResponse.objects.filter(
            survey=self.survey, user=self.user
        ).exists():
            self.add_error(
                None,
                "You have already submitted a response. Please edit the other instead.",
            )
        return cleaned_data

    @transaction.atomic
    def save(self):
        cleaned_data = super().clean()

        user_survey_response = UserSurveyResponse.objects.create(
            survey=self.survey, user=self.user
        )

        question_responses = [
            UserQuestionResponse(
                question=question,
                user_survey_response=user_survey_response,
                value=get_response_value(cleaned_data, question),
            )
            for question in self.questions
        ]
        UserQuestionResponse.objects.bulk_create(
            question_responses,
            update_conflicts=True,
            update_fields=("value",),
            unique_fields=("question", "user_survey_response"),
        )
        return user_survey_response


class EditUserSurveyResponseForm(BaseSurveyForm):
    def __init__(self, *args, instance, **kwargs):
        self.survey = instance.survey
        self.user_survey_response = instance
        super().__init__(*args, survey=self.survey, user=instance.user, **kwargs)
        self._set_initial_data()

    def _set_initial_data(self):
        question_responses = self.user_survey_response.userquestionresponse_set.all()

        for question_response in question_responses:
            field_name = to_field_name(question_response.question)
            if question_response.question.type_field == TypeField.MULTI_SELECT:
                self.fields[field_name].initial = question_response.value.split(",")
            else:
                self.fields[field_name].initial = question_response.value

    def clean(self):
        cleaned_data = super().clean()
        if not self.user_survey_response.is_editable():
            self.add_error(None, "You are no longer able to edit this.")
        return cleaned_data

    @transaction.atomic
    def save(self):
        cleaned_data = super().clean()

        question_responses = [
            UserQuestionResponse(
                question=question,
                user_survey_response=self.user_survey_response,
                value=get_response_value(cleaned_data, question),
            )
            for question in self.questions
        ]
        UserQuestionResponse.objects.bulk_create(
            question_responses,
            update_conflicts=True,
            update_fields=("value",),
            unique_fields=("question", "user_survey_response"),
        )
        return self.user_survey_response
