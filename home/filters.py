"""
Django filters for team formation and applicant filtering.
"""

from typing import Optional

import django_filters
from django import forms
from django.db.models import QuerySet, Exists, OuterRef

from accounts.models import CustomUser
from home.models import Project, Team, UserSurveyResponse


class BooleanFilter(django_filters.BooleanFilter):
    field_class = forms.BooleanField


class ApplicantFilterSet(django_filters.FilterSet):
    """FilterSet for filtering applicants in team formation view."""

    score_min = django_filters.NumberFilter(
        field_name="score", lookup_expr="gte", label="Minimum Score"
    )
    score_max = django_filters.NumberFilter(
        field_name="score", lookup_expr="lte", label="Maximum Score"
    )

    rank_min = django_filters.NumberFilter(
        field_name="selection_rank", lookup_expr="gte", label="Minimum Selection Rank"
    )
    rank_max = django_filters.NumberFilter(
        field_name="selection_rank", lookup_expr="lte", label="Maximum Selection Rank"
    )

    team = django_filters.ModelChoiceFilter(
        field_name="user__session_memberships__team",
        queryset=Team.objects.none(),
        label="Team Assignment",
        method="filter_by_team",
    )

    show_unassigned_only = BooleanFilter(
        method="filter_unassigned",
        label="Show only unassigned applicants",
        widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}),
    )

    overlap_with_navigators = django_filters.ModelChoiceFilter(
        queryset=Team.objects.none(),
        label="Has overlap with navigators",
        method="filter_navigator_overlap",
    )

    overlap_with_captain = django_filters.ModelChoiceFilter(
        queryset=Team.objects.none(),
        label="Has overlap with captain",
        method="filter_captain_overlap",
    )

    project_preference = django_filters.ModelChoiceFilter(
        queryset=Project.objects.none(),
        label="Project Preference",
        method="filter_by_project_preference",
    )

    class Meta:
        model = UserSurveyResponse
        fields = []

    def __init__(self, *args, session=None, **kwargs):
        """Initialize with session context for team querysets."""
        super().__init__(*args, **kwargs)
        self.session = session

        if session:
            # Populate team querysets for this session
            team_queryset = session.teams.all().order_by("name")
            self.filters["team"].queryset = team_queryset
            self.filters["overlap_with_navigators"].queryset = team_queryset
            self.filters["overlap_with_captain"].queryset = team_queryset

            # Populate project queryset with session's available projects
            self.filters["project_preference"].queryset = (
                session.available_projects.all()
            )

    def filter_by_team(
        self, queryset: QuerySet, name: str, value: Team | None
    ) -> QuerySet:
        """Filter applicants by specific team assignment."""
        if value and self.session:
            return queryset.with_team_assignment(value, self.session)
        return queryset

    def filter_unassigned(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        """Filter to show only unassigned applicants."""
        # BooleanFilter will pass True, False, or None
        # We only want to filter when explicitly True
        if value is True and self.session:
            return queryset.without_team_assignment(self.session)
        return queryset

    def filter_navigator_overlap(
        self, queryset: QuerySet, name: str, value: Team | None
    ) -> QuerySet:
        """Filter applicants by availability overlap with team navigators."""
        if value:
            return queryset.with_navigator_overlap(value)
        return queryset

    def filter_captain_overlap(
        self, queryset: QuerySet, name: str, value: Team | None
    ) -> QuerySet:
        """Filter applicants by availability overlap with team captain."""
        if value and self.session:
            return queryset.with_captain_overlap(value)
        return queryset

    def filter_by_project_preference(
        self, queryset: QuerySet, name: str, value: Project | None
    ) -> QuerySet:
        """Filter applicants by their project preferences."""
        if value and self.session:
            users_with_preference = CustomUser.objects.with_project_preference(
                project=value,
                session=self.session,
            )
            return queryset.filter(
                Exists(users_with_preference.filter(user_id=OuterRef("id")))
            )
        return queryset
