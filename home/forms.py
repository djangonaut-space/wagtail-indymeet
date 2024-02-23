from __future__ import annotations

from typing import List, Tuple

from django import forms
from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.db import models, transaction
from django.db.models.fields import CharField, EmailField
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from wagtail.admin.edit_handlers import FieldPanel, InlinePanel
from wagtail.contrib.forms.models import AbstractForm, AbstractFormField
from wagtail.core.fields import RichTextField
from wagtail.snippets.models import register_snippet

from home.constants import DATE_INPUT_FORMAT, SURVEY_FIELD_VALIDATORS
from home.models import Question, TypeField, UserQuestionResponse, UserSurveyResponse
from home.validators import RatingValidator
from home.widgets import (
    CheckboxSelectMultipleSurvey,
    DateSurvey,
    RadioSelectSurvey,
    RatingSurvey,
)


class TestForm(forms.Form):
    test_input = forms.CharField(max_length=255)


class SignUpField(AbstractFormField):
    page = ParentalKey(
        "SignUpPage", on_delete=models.CASCADE, related_name="form_fields"
    )


@register_snippet
class SignUpPage(AbstractForm):
    template_name = "forms/sign_up.html"
    name = CharField(max_length=255, blank=True)
    email = EmailField(max_length=255, blank=True)
    thank_you_text = RichTextField(blank=True)

    content_panels = AbstractForm.content_panels + [
        FieldPanel("name"),
        InlinePanel("form_fields", label="Form fields"),
        FieldPanel("thank_you_text"),
    ]

    def get_template(self, request):
        return self.template_name

    def get_context_data(self, request):
        context = super().get_context(request)
        return context


def make_choices(question: Question) -> List[Tuple[str, str]]:
    choices = []
    for choice in question.choices.split(","):
        choice = choice.strip()
        choices.append((choice.replace(" ", "_").lower(), choice))
    return choices


class BaseSurveyForm(forms.Form):

    def __init__(self, survey, user, *args, **kwargs):
        self.survey = survey
        self.user = user if user.is_authenticated else None
        self.field_names = []
        self.questions = self.survey.questions.all().order_by("ordering")
        super().__init__(*args, **kwargs)

        for question in self.questions:
            # to generate field name
            field_name = f"field_survey_{question.id}"

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

    @transaction.atomic
    def save(self):
        cleaned_data = super().clean()

        user_survey_response = UserSurveyResponse.objects.create(
            survey=self.survey, user=self.user
        )
        for question in self.questions:
            field_name = f"field_survey_{question.id}"

            if question.type_field == TypeField.MULTI_SELECT:
                value = ",".join(cleaned_data[field_name])
            else:
                value = cleaned_data[field_name]

            UserQuestionResponse.objects.create(
                question=question,
                value=value,
                user_survey_response=user_survey_response,
            )
