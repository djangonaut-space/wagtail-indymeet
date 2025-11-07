import csv
import io

from django import forms
from django.core import validators
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MaxLengthValidator
from django.core.validators import MinLengthValidator
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import CustomUser
from home.constants import DATE_INPUT_FORMAT
from home.constants import SURVEY_FIELD_VALIDATORS
from home.models import Question, Team, SessionMembership, ProjectPreference
from home.models import Survey
from home.models import TypeField
from home.models import UserQuestionResponse
from home.models import UserSurveyResponse
from home.availability import (
    calculate_overlap,
    calculate_team_overlap,
    format_slots_as_ranges,
)
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

        # Add all question fields first
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
                        ),
                        MaxLengthValidator(
                            SURVEY_FIELD_VALIDATORS["max_length"]["text_area"]
                        ),
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

        # Add project preference field if survey is associated with a session
        self.session = None
        try:
            app_session = self.survey.application_session
        except ObjectDoesNotExist:
            pass
        else:
            if app_session.is_accepting_applications():
                self.session = app_session

                # Add project preference field if session has available projects
                project_choices = [
                    (project.id, project.name)
                    for project in self.session.available_projects.all()
                ]
                if project_choices:
                    self.fields["project_preferences"] = forms.MultipleChoiceField(
                        choices=project_choices,
                        label=_("Project Preferences"),
                        help_text=_(
                            "Select the projects you would like to work on. "
                            "Leave blank if you're okay with any project."
                        ),
                        widget=CheckboxSelectMultipleSurvey,
                        required=False,
                    )

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

        # Save project preferences if provided and session exists
        if self.session and (
            project_preferences := cleaned_data.get("project_preferences")
        ):
            preferences = [
                ProjectPreference(
                    user=self.user,
                    session=self.session,
                    project_id=project_id,
                )
                for project_id in project_preferences
            ]
            ProjectPreference.objects.bulk_create(preferences, ignore_conflicts=True)

        return user_survey_response


class EditUserSurveyResponseForm(BaseSurveyForm):
    def __init__(self, *args, instance: UserSurveyResponse, **kwargs):
        self.user_survey_response = instance
        super().__init__(*args, survey=instance.survey, user=instance.user, **kwargs)
        self._set_initial_data()

    def _set_initial_data(self):

        question_responses = self.user_survey_response.userquestionresponse_set.all()

        for question_response in question_responses:
            field_name = to_field_name(question_response.question)
            if question_response.question.type_field == TypeField.MULTI_SELECT:
                self.fields[field_name].initial = question_response.value.split(",")
            else:
                self.fields[field_name].initial = question_response.value

        # Set initial data for project preferences
        if self.session and "project_preferences" in self.fields:
            existing_prefs = ProjectPreference.objects.for_user_session(
                user=self.user_survey_response.user, session=self.session
            ).values_list("project_id", flat=True)
            self.fields["project_preferences"].initial = list(existing_prefs)

    def clean(self):
        cleaned_data = super().clean()
        if not self.user_survey_response.is_editable():
            self.add_error(None, "You are no longer able to edit this.")
        return cleaned_data

    @transaction.atomic
    def save(self):
        cleaned_data = super().clean()
        self.user_survey_response.updated_at = timezone.now()
        self.user_survey_response.save(update_fields=["updated_at"])

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

        # Update project preferences if session exists
        if self.session and (
            project_preferences := cleaned_data.get("project_preferences")
        ):
            # Delete existing preferences for this user/session
            ProjectPreference.objects.for_user_session(
                user=self.user_survey_response.user, session=self.session
            ).exclude(project_id__in=project_preferences).delete()

            # Create new preferences if projects were selected
            preferences = [
                ProjectPreference(
                    user=self.user_survey_response.user,
                    session=self.session,
                    project_id=project_id,
                )
                for project_id in project_preferences
            ]
            ProjectPreference.objects.bulk_create(preferences, ignore_conflicts=True)

        return self.user_survey_response


class SurveyCSVExportForm(forms.Form):
    """Form for generating CSV export with scorer columns"""

    scorer_names = forms.CharField(
        label=_("Scorer Names"),
        widget=forms.Textarea(attrs={"rows": 5, "cols": 40}),
        required=False,
        help_text=_(
            "Enter one scorer name per line. These will be added as "
            "empty columns in the CSV for external scoring."
        ),
    )

    def clean_scorer_names(self) -> list[str]:
        """Parse scorer names from textarea input"""
        scorer_names_text = self.cleaned_data.get("scorer_names", "")
        if not scorer_names_text.strip():
            return []

        # Split by newlines and strip whitespace
        scorers = [
            name.strip() for name in scorer_names_text.split("\n") if name.strip()
        ]
        return scorers

    def generate_csv(self, survey: Survey, request_data: dict) -> HttpResponse:
        """
        Generate CSV based on which button was clicked.

        Args:
            survey: The survey to export
            request_data: POST data to check which button was clicked

        Returns:
            HttpResponse with CSV file
        """
        if "generate_scorer_csv" in request_data:
            return self.generate_single_scorer_csv(survey)
        else:
            return self.generate_full_csv(survey)

    def generate_full_csv(self, survey: Survey) -> HttpResponse:
        """Generate CSV file with survey responses and scorer columns"""
        scorer_names = self.cleaned_data.get("scorer_names", [])

        # Get all responses for this survey with related data
        responses = (
            UserSurveyResponse.objects.filter(survey=survey)
            .select_related("user")
            .prefetch_related("userquestionresponse_set__question")
            .order_by("id")
        )

        # Get all questions for this survey
        questions = survey.questions.all().order_by("ordering")

        # Create the HTTP response with CSV headers (UTF-8 encoded)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="survey_{survey.slug}_responses.csv"'
        )
        # Add UTF-8 BOM to ensure Excel and other tools properly recognize UTF-8
        response.write("\ufeff")

        writer = csv.writer(response)

        # Write header row
        header = ["Response ID", "Submitter Name"]
        # Add question labels as columns
        header.extend([q.label for q in questions])
        # Add scorer columns
        header.extend([f"{name} score" for name in scorer_names])
        # Add Score and Selection Rank columns
        header.append("Score")
        header.append("Selection Rank")
        writer.writerow(header)

        # Write data rows
        for response_obj in responses:
            row = [
                response_obj.id,
                f"{response_obj.user.first_name} {response_obj.user.last_name}".strip()
                or response_obj.user.email,
            ]

            # Get all question responses for this survey response
            question_responses = {
                qr.question_id: qr.value
                for qr in response_obj.userquestionresponse_set.all()
            }

            # Add question responses in order
            for question in questions:
                row.append(question_responses.get(question.id, ""))

            # Add empty scorer columns
            row.extend([""] * len(scorer_names))

            # Add empty Score and Selection Rank columns
            row.append("")
            row.append("")

            writer.writerow(row)

        return response

    def generate_single_scorer_csv(self, survey: Survey) -> HttpResponse:
        """
        Generate anonymized Single Scorer CSV with only TEXT_AREA questions.
        Suitable for session organizers to score anonymously.
        """
        # Get all responses for this survey with related data
        responses = (
            UserSurveyResponse.objects.filter(survey=survey)
            .select_related("user")
            .prefetch_related("userquestionresponse_set__question")
            .order_by("id")
        )

        # Get only TEXT_AREA questions
        questions = survey.questions.filter(type_field=TypeField.TEXT_AREA).order_by(
            "ordering"
        )

        # Create the HTTP response with CSV headers (UTF-8 encoded)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="survey_{survey.slug}_single_scorer.csv"'
        )
        # Add UTF-8 BOM to ensure Excel and other tools properly recognize UTF-8
        response.write("\ufeff")

        writer = csv.writer(response)

        # Write header row - only Response ID and TEXT_AREA questions
        header = ["Response ID"]
        # Add question labels as columns
        header.extend([q.label for q in questions])
        # Add Score and Selection Rank columns (no individual scorer columns)
        header.append("Score")
        header.append("Selection Rank")
        writer.writerow(header)

        # Write data rows
        for response_obj in responses:
            row = [response_obj.id]

            # Get all question responses for this survey response
            question_responses = {
                qr.question_id: qr.value
                for qr in response_obj.userquestionresponse_set.all()
            }

            # Add only TEXT_AREA question responses in order
            for question in questions:
                row.append(question_responses.get(question.id, ""))

            # Add empty Score and Selection Rank columns
            row.append("")
            row.append("")

            writer.writerow(row)

        return response


class SurveyCSVImportForm(forms.Form):
    """Form for importing scores from a CSV file"""

    csv_file = forms.FileField(
        label=_("CSV File"),
        validators=[validators.FileExtensionValidator(["csv"])],
        required=True,
        help_text=_(
            "Upload a CSV file with 'Response ID', 'Score', and 'Selection Rank' columns. "
            "Only these columns will be processed; all other columns will be ignored."
        ),
    )

    def clean_csv_file(self) -> list[tuple[int, int, int]]:
        """
        Parse and validate the CSV file.

        Returns:
            List of tuples (response_id, score, selection_rank) for valid rows.
            All three values are required integers.

        Raises:
            forms.ValidationError: If CSV is invalid or missing required columns
        """
        csv_file = self.cleaned_data.get("csv_file")
        if not csv_file:
            raise forms.ValidationError(_("No file was uploaded."))

        # Check file extension
        if not csv_file.name.endswith(".csv"):
            raise forms.ValidationError(_("File must be a CSV file."))

        try:
            # Read the file content and decode it
            file_content = csv_file.read().decode("utf-8-sig")  # utf-8-sig handles BOM
            csv_file.seek(0)  # Reset file pointer for potential re-reading

            # Parse CSV
            reader = csv.DictReader(io.StringIO(file_content))

            # Validate required columns exist
            if not reader.fieldnames:
                raise forms.ValidationError(_("CSV file is empty or has no headers."))

            required_columns = ["Response ID", "Score", "Selection Rank"]
            for column in required_columns:
                if column not in reader.fieldnames:
                    raise forms.ValidationError(
                        _(f"CSV file must contain a '{column}' column.")
                    )

            # Parse and validate rows
            updates = []
            errors = []
            row_number = 1  # Start at 1 for header, increment for data rows

            for row in reader:
                row_number += 1
                response_id_str = row.get("Response ID", "").strip()
                score_str = row.get("Score", "").strip()
                selection_rank_str = row.get("Selection Rank", "").strip()

                # Skip rows with empty Response ID, Score, or Selection Rank
                if not response_id_str or not score_str or not selection_rank_str:
                    continue

                # Validate Response ID is an integer
                try:
                    response_id = int(response_id_str)
                except ValueError:
                    errors.append(
                        _(
                            f"Row {row_number}: Invalid Response ID '{response_id_str}' "
                            "(must be an integer)"
                        )
                    )
                    continue

                # Validate Score is an integer
                try:
                    score = int(score_str)
                except ValueError:
                    errors.append(
                        _(
                            f"Row {row_number}: Invalid Score '{score_str}' (must be an integer)"
                        )
                    )
                    continue

                # Validate Selection Rank is an integer (required)
                try:
                    selection_rank = int(selection_rank_str)
                except ValueError:
                    errors.append(
                        _(
                            f"Row {row_number}: Invalid Selection Rank '{selection_rank_str}' "
                            "(must be an integer)"
                        )
                    )
                    continue

                updates.append((response_id, score, selection_rank))

            # Report errors if any
            if errors:
                raise forms.ValidationError(errors)

            # Ensure we have at least one valid row
            if not updates:
                raise forms.ValidationError(
                    "No valid data rows found. Ensure the CSV has 'Response ID', "
                    "'Score', and 'Selection Rank' columns with valid integer values."
                )

            return updates

        except UnicodeDecodeError:
            raise forms.ValidationError(
                "File encoding error. Please ensure the file is UTF-8 encoded."
            )
        except csv.Error as e:
            raise forms.ValidationError(f"CSV parsing error: {e}")

    def import_scores(self, survey: Survey) -> dict:
        """
        Import scores from the validated CSV data.

        Args:
            survey: The survey to import scores for

        Returns:
            Dictionary with import statistics:
                - updated: Number of responses updated
        """
        updates = self.cleaned_data.get("csv_file")
        if not updates:
            return {"updated": 0}

        response_ids = [response_id for response_id, _, _ in updates]
        score_map = {response_id: score for response_id, score, _ in updates}
        selection_rank_map = {
            response_id: selection_rank for response_id, _, selection_rank in updates
        }

        # Fetch all relevant UserSurveyResponse objects for this survey only
        existing_responses = UserSurveyResponse.objects.filter(
            id__in=response_ids,
            survey=survey,
        )

        # Update scores and selection_rank using a transaction
        updated_count = 0
        with transaction.atomic():
            for response in existing_responses.select_for_update():
                response.score = score_map[response.id]
                response.selection_rank = selection_rank_map[response.id]
                response.save(update_fields=["score", "selection_rank"])
                updated_count += 1

        return {"updated": updated_count}


# Team Formation Forms


class ApplicantFilterForm(forms.Form):
    """Form for filtering applicants by various criteria."""

    score_min = forms.IntegerField(
        label=_("Minimum Score"),
        required=False,
        widget=forms.NumberInput(
            attrs={"class": "form-input", "placeholder": "e.g., 0"}
        ),
    )
    score_max = forms.IntegerField(
        label=_("Maximum Score"),
        required=False,
        widget=forms.NumberInput(
            attrs={"class": "form-input", "placeholder": "e.g., 10"}
        ),
    )

    rank_min = forms.IntegerField(
        label=_("Minimum Selection Rank"),
        required=False,
        widget=forms.NumberInput(
            attrs={"class": "form-input", "placeholder": "e.g., 1"}
        ),
    )
    rank_max = forms.IntegerField(
        label=_("Maximum Selection Rank"),
        required=False,
        widget=forms.NumberInput(
            attrs={"class": "form-input", "placeholder": "e.g., 50"}
        ),
    )

    team = forms.ModelChoiceField(
        label=_("Team Assignment"),
        queryset=None,
        required=False,
        empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    show_unassigned_only = forms.BooleanField(
        label=_("Show only unassigned applicants"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}),
    )

    overlap_with_navigators = forms.ModelChoiceField(
        label=_("Has overlap with navigators"),
        queryset=None,
        required=False,
        empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text=_(
            "Show only applicants with availability overlap with team navigators"
        ),
    )

    overlap_with_captain = forms.ModelChoiceField(
        label=_("Has overlap with captain"),
        queryset=None,
        required=False,
        empty_label=_("All"),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text=_("Show only applicants with availability overlap with team captain"),
    )

    def __init__(self, *args, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session

        if session:
            # Populate team choices for this session
            team_queryset = session.teams.all().order_by("name")
            self.fields["team"].queryset = team_queryset
            self.fields["overlap_with_navigators"].queryset = team_queryset
            self.fields["overlap_with_captain"].queryset = team_queryset


class OverlapAnalysisForm(forms.Form):
    """Form for analyzing availability overlap between selected users and team members."""

    prefix = "overlap"

    user_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
        help_text=_("Comma-separated list of user IDs to analyze"),
    )

    team = forms.ModelChoiceField(
        label=_("Team"),
        queryset=None,
        required=True,
        help_text=_("Team whose navigators/captain will be included in analysis"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    analysis_type = forms.ChoiceField(
        label=_("Analysis Type"),
        choices=[
            ("overlap-navigator", _("Check Navigator Overlap")),
            ("overlap-captain", _("Check Captain Overlap")),
        ],
        initial="overlap-navigator",
        widget=forms.RadioSelect(attrs={"class": "form-radio"}),
    )

    def __init__(self, *args, session=None, **kwargs):
        """Initialize form with session context for team queryset."""
        super().__init__(*args, **kwargs)
        self.session = session
        if session:
            self.fields["team"].queryset = Team.objects.filter(
                session=session
            ).order_by("name")

    def clean_user_ids(self) -> list[int]:
        """Parse and validate user IDs."""

        user_ids_str = self.cleaned_data.get("user_ids", "")
        if not user_ids_str:
            raise forms.ValidationError(_("No users selected"))

        try:
            user_ids = [
                int(uid.strip()) for uid in user_ids_str.split(",") if uid.strip()
            ]
        except ValueError:
            raise forms.ValidationError(_("Invalid user ID format"))

        if not user_ids:
            raise forms.ValidationError(_("No users selected"))

        # Verify users exist
        existing_count = CustomUser.objects.filter(id__in=user_ids).count()
        if existing_count != len(user_ids):
            raise forms.ValidationError(_("Some selected users do not exist"))

        return user_ids

    def get_selected_users(self) -> list[CustomUser]:
        """
        Get selected users with prefetched availability.

        Returns:
            List of CustomUser instances with availability prefetched
        """
        user_ids = self.cleaned_data["user_ids"]
        return list(
            CustomUser.objects.filter(id__in=user_ids).prefetch_related("availability")
        )

    def get_team_navigators(self) -> list[CustomUser]:
        """
        Get navigators from the selected team.

        Returns:
            List of navigator users with availability prefetched

        Raises:
            forms.ValidationError: If team has no navigators
        """
        team = self.cleaned_data["team"]
        navigator_memberships = (
            SessionMembership.objects.filter(
                team=team, role=SessionMembership.NAVIGATOR
            )
            .select_related("user")
            .prefetch_related("user__availability")
        )

        navigators = [m.user for m in navigator_memberships]

        if not navigators:
            raise forms.ValidationError(
                f"Team '{team.name}' has no navigators assigned"
            )

        return navigators

    def get_team_captain(self) -> CustomUser:
        """
        Get captain from the selected team.

        Returns:
            Captain user with availability prefetched

        Raises:
            forms.ValidationError: If team has no captain
        """
        team = self.cleaned_data["team"]
        captain_memberships = (
            SessionMembership.objects.filter(team=team, role=SessionMembership.CAPTAIN)
            .select_related("user")
            .prefetch_related("user__availability")
        )

        captains = [m.user for m in captain_memberships]

        if not captains:
            raise forms.ValidationError(f"Team '{team.name}' has no captain assigned")

        return captains[0]  # Use first captain if multiple

    def calculate_navigator_overlap_context(self) -> dict:
        """
        Calculate navigator overlap (navigators + selected users).

        Returns:
            Context dictionary with overlap analysis results
        """
        team = self.cleaned_data["team"]
        navigators = self.get_team_navigators()
        selected_users = self.get_selected_users()

        # Calculate navigator overlap (navigators + selected users)
        all_users = navigators + selected_users
        slots, hours = calculate_overlap(all_users)
        time_ranges = format_slots_as_ranges(slots)

        return {
            "team": team,
            "analysis_type": "overlap-navigator",
            "navigators": navigators,
            "selected_users": selected_users,
            "hour_blocks": hours,
            "time_ranges": time_ranges,
            "is_sufficient": hours >= 5,
        }

    def calculate_captain_overlap_context(self) -> dict:
        """
        Calculate captain overlaps (with each selected user).

        Returns:
            Context dictionary with overlap analysis results
        """
        team = self.cleaned_data["team"]
        captain = self.get_team_captain()
        selected_users = self.get_selected_users()

        # Calculate captain overlaps (with each selected user)
        results = []
        for user in selected_users:
            slots, hours = calculate_overlap([captain, user])
            time_ranges = format_slots_as_ranges(slots)
            results.append(
                {
                    "user": user,
                    "hour_blocks": hours,
                    "time_ranges": time_ranges,
                    "is_sufficient": hours >= 2,
                }
            )

        return {
            "team": team,
            "analysis_type": "overlap-captain",
            "captain": captain,
            "results": results,
        }

    def get_overlap_context(self) -> dict:
        """
        Get overlap analysis context based on analysis type.

        Returns:
            Context dictionary for template rendering

        Raises:
            forms.ValidationError: If team members are missing
        """
        analysis_type = self.cleaned_data["analysis_type"]

        if analysis_type == "overlap-navigator":
            return self.calculate_navigator_overlap_context()
        else:  # captain
            return self.calculate_captain_overlap_context()


class BulkTeamAssignmentForm(forms.Form):
    """Form for bulk assignment of users to a team."""

    prefix = "bulk_assign"

    user_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
        help_text=_("Comma-separated list of user IDs to assign"),
    )

    team = forms.ModelChoiceField(
        label=_("Team"),
        queryset=None,
        required=True,
        empty_label=_("-- Choose Team --"),
        widget=forms.Select(attrs={"class": "form-select", "id": "bulk-team-select"}),
        help_text=_("Select the team to assign selected users to"),
    )

    def __init__(self, *args, session=None, **kwargs):
        """Initialize form with session context for team queryset."""
        super().__init__(*args, **kwargs)
        self.session = session
        if session:

            self.fields["team"].queryset = Team.objects.filter(
                session=session
            ).order_by("name")

    def clean_user_ids(self) -> list[int]:
        """Parse and validate user IDs."""

        user_ids_str = self.cleaned_data.get("user_ids", "")
        if not user_ids_str:
            raise forms.ValidationError(_("No users selected"))

        try:
            user_ids = [
                int(uid.strip()) for uid in user_ids_str.split(",") if uid.strip()
            ]
        except ValueError:
            raise forms.ValidationError(_("Invalid user ID format"))

        if not user_ids:
            raise forms.ValidationError(_("No users selected"))

        # Verify users exist
        existing_count = CustomUser.objects.filter(id__in=user_ids).count()
        if existing_count != len(user_ids):
            raise forms.ValidationError(_("Some selected users do not exist"))

        return user_ids

    def clean(self):
        """Validate that users' project preferences match the team's project."""
        cleaned_data = super().clean()

        # Only validate if we have both user_ids and team
        if "user_ids" not in cleaned_data or "team" not in cleaned_data:
            return cleaned_data

        user_ids = cleaned_data["user_ids"]
        team = cleaned_data["team"]

        # Get users who have invalid/conflicting project preferences
        users_with_invalid_pref = CustomUser.objects.filter(
            id__in=user_ids
        ).with_invalid_project_preference(
            project=team.project,
            session=self.session,
        )

        # Build error message if any users have mismatched preferences
        user_list = ", ".join(
            user.get_full_name() or user.email for user in users_with_invalid_pref
        )
        if user_list:
            self.add_error(
                "team",
                _(
                    f"The following users have not selected '{team.project.name}'"
                    f"as a preference: {user_list}. Users with no preferences can "
                    "be assigned to any project."
                ),
            )

        return cleaned_data

    @transaction.atomic
    def save(self) -> int:
        """
        Assign selected users to the team.

        Returns:
            Number of users successfully assigned
        """

        if not self.session:
            raise ValueError("Session must be set before saving")

        user_ids = self.cleaned_data["user_ids"]
        team = self.cleaned_data["team"]

        assigned_count = 0
        for user_id in user_ids:
            try:
                user = CustomUser.objects.get(pk=user_id)
                membership, created = SessionMembership.objects.get_or_create(
                    user=user,
                    session=self.session,
                    defaults={"role": SessionMembership.DJANGONAUT},
                )
                membership.team = team
                # Don't change role - keep whatever it was
                membership.save()
                assigned_count += 1
            except CustomUser.DoesNotExist:
                continue

        return assigned_count
