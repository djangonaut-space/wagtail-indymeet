"""
Dataclasses for structured data in team formation views.

These dataclasses replace unbounded dictionaries to provide better type safety
and IDE support.
"""

from dataclasses import dataclass
from typing import Optional

from accounts.models import CustomUser
from home.models import Project, Team, UserSurveyResponse


@dataclass
class ApplicantData:
    """Data for a single applicant in the team formation view."""

    user: CustomUser
    response: UserSurveyResponse
    score: int | None
    selection_rank: int | None
    current_team: Team | None
    current_role: str | None
    is_waitlisted: bool
    previous_application_count: int
    previous_avg_score: float | None
    has_availability: bool
    availability_by_day: dict[str, list[str]]  # Day name -> time ranges
    project_preferences: list[Project]  # List of preferred projects


@dataclass
class DjangonautDetail:
    """Details for a djangonaut in a team."""

    user: CustomUser
    score: int | None
    selection_rank: int | None
    captain_hours: int | None


@dataclass
class TeamStatistics:
    """Statistics and member information for a team."""

    team: Team
    navigators: list[CustomUser]
    captain: CustomUser | None
    djangonaut_details: list[DjangonautDetail]
    navigator_meeting_hours: int
    captain_meetings: list[dict]  # Keep as dict since it comes from utils
    is_valid: bool
