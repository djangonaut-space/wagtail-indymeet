"""
Django filters for team formation and applicant filtering.
"""

from typing import Optional

import django_filters
from django import forms
from django.db.models import QuerySet, Exists, OuterRef

from accounts.models import CustomUser
from home.models import Project, Team, UserSurveyResponse, Waitlist


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

    exclude_waitlisted = BooleanFilter(
        method="filter_exclude_waitlisted",
        label="Hide waitlisted applicants",
        widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}),
    )

    show_waitlisted_only = BooleanFilter(
        method="filter_waitlisted_only",
        label="Show only waitlisted applicants",
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

    def filter_exclude_waitlisted(
        self, queryset: QuerySet, name: str, value: bool
    ) -> QuerySet:
        """Exclude waitlisted applicants from results."""
        if value is True and self.session:
            # Get user IDs that are waitlisted for this session
            waitlisted_user_ids = Waitlist.objects.filter(
                session=self.session
            ).values_list("user_id", flat=True)
            return queryset.exclude(user_id__in=waitlisted_user_ids)
        return queryset

    def filter_waitlisted_only(
        self, queryset: QuerySet, name: str, value: bool
    ) -> QuerySet:
        """Show only waitlisted applicants."""
        if value is True and self.session:
            # Get user IDs that are waitlisted for this session
            waitlisted_user_ids = Waitlist.objects.filter(
                session=self.session
            ).values_list("user_id", flat=True)
            return queryset.filter(user_id__in=waitlisted_user_ids)
        return queryset
