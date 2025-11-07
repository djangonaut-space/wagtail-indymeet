"""
Team formation admin view for creating and managing teams within a session.

This view provides an interface for:
- Viewing and filtering applicants
- Analyzing availability overlaps
- Forming teams with validation
- Viewing current team compositions and statistics
"""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from home.dataclasses import ApplicantData, DjangonautDetail, TeamStatistics
from home.filters import ApplicantFilterSet
from home.forms import BulkTeamAssignmentForm, OverlapAnalysisForm
from home.models import Session, SessionMembership, Team, UserSurveyResponse
from home.availability import (
    calculate_team_overlap,
    format_availability_by_day,
)


@permission_required("Team.form_team")
@staff_member_required
@require_http_methods(["GET", "POST"])
def team_formation_view(request: HttpRequest, session_id: int) -> HttpResponse:
    """
    Main view for team formation interface.

    Displays:
    - Applicant list with filtering and pagination
    - Quick team assignment actions
    - Current teams with statistics
    """
    session = get_object_or_404(
        Session.objects.select_related("application_survey"), pk=session_id
    )

    # Handle bulk team assignment
    if request.method == "POST":
        bulk_form = BulkTeamAssignmentForm(request.POST, session=session)
        if bulk_form.is_valid():
            assigned_count = bulk_form.save()
            team = bulk_form.cleaned_data["team"]
            messages.success(
                request,
                f"Successfully assigned {assigned_count} user(s) to team '{team.name}'.",
            )
            return redirect("admin:session_form_teams", session_id=session.id)
        # If form is invalid, errors will be displayed in the template
    else:
        bulk_form = BulkTeamAssignmentForm(session=session)

    # Get sorting parameters
    sort_by = request.GET.get("sort", "selection_rank")
    sort_order = request.GET.get("order", "asc")

    # Build applicant queryset with filtering and sorting
    applicants_list, filterset = get_filtered_applicants(
        session, request.GET, sort_by, sort_order
    )

    # Paginate applicants
    page_number = request.GET.get("page", 1)
    paginator = Paginator(applicants_list, 25)  # 25 per page
    page_obj = paginator.get_page(page_number)

    # Get current teams with statistics
    teams_data = get_teams_with_statistics(session)

    # Create overlap analysis form
    overlap_form = OverlapAnalysisForm(session=session)

    context = {
        "session": session,
        "filter_form": filterset.form,  # Use the form from the filterset
        "overlap_form": overlap_form,
        "bulk_form": bulk_form,
        "page_obj": page_obj,
        "teams": teams_data,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "days_of_week": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "min_navigator_hours": Team.MIN_NAVIGATOR_MEETING_HOURS,
        "sort_config": {
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
        "min_captain_hours": Team.MIN_CAPTAIN_OVERLAP_HOURS,
        "opts": Session._meta,
        "has_view_permission": True,
        "site_title": "Django Administration",
        "site_header": "Django Administration",
    }

    return render(request, "admin/team_formation.html", context)


@permission_required("Team.form_team")
@staff_member_required
@require_http_methods(["POST"])
def calculate_overlap_ajax(request: HttpRequest, session_id: int) -> HttpResponse:
    """
    AJAX endpoint (htmx) for calculating availability overlap.

    Returns HTML fragment showing overlap analysis results.
    """
    session = get_object_or_404(Session, pk=session_id)
    # Validate form
    form = OverlapAnalysisForm(request.POST, session=session)
    if form.is_valid():
        # Get overlap analysis context from form
        context = form.get_overlap_context()
    else:
        context = {"form": form}
    return render(request, "admin/partials/overlap_results.html", context)


def get_filtered_applicants(
    session: Session,
    request_data,
    sort_by: str = "selection_rank",
    sort_order: str = "asc",
) -> tuple[list[ApplicantData], "ApplicantFilterSet"]:
    """
    Get applicants with optional filtering, sorting, and annotated metadata.

    Args:
        session: The session to get applicants for
        request_data: GET parameters for filtering
        sort_by: Field to sort by (score, selection_rank, annotated_previous_application_count)
        sort_order: Sort direction ('asc' or 'desc')

    Returns a tuple of (applicants, filterset) where:
    - applicants: List of ApplicantData dataclass instances
    - filterset: The ApplicantFilterSet used for filtering

    This function uses QuerySet methods to avoid N+1 queries.
    """
    # Check application_survey_id first to avoid DB hit when not set
    if not session.application_survey_id:
        # Return empty list and an unbound filterset
        filterset = ApplicantFilterSet(
            data=None,
            queryset=UserSurveyResponse.objects.none(),
            session=session,
        )
        return [], filterset

    # Use QuerySet method to get all team formation data
    applicants_qs = UserSurveyResponse.objects.with_full_team_formation_data(session)

    # Use django-filter for filtering
    filterset = ApplicantFilterSet(
        data=request_data or None,
        queryset=applicants_qs,
        session=session,
    )
    applicants_qs = filterset.qs

    # Apply database-level sorting
    # Nulls always go last regardless of sort order using Django's nulls_last/nulls_first
    if sort_by in ["score", "selection_rank", "annotated_previous_application_count"]:
        from django.db.models import F

        order_field = F(sort_by)
        if sort_order == "desc":
            applicants_qs = applicants_qs.order_by(order_field.desc(nulls_last=True))
        else:
            applicants_qs = applicants_qs.order_by(order_field.asc(nulls_last=True))

    # Build applicant data list
    applicants = []
    for response in applicants_qs:
        user = response.user

        # Get current team assignment from prefetched data
        current_team = None
        current_role = None
        if (
            hasattr(user, "prefetched_current_session_memberships")
            and user.prefetched_current_session_memberships
        ):
            membership = user.prefetched_current_session_memberships[0]
            current_team = membership.team
            current_role = membership.role

        # Get availability data
        availability_slots = []
        availability_by_day = {}
        has_availability = response.annotated_has_availability

        if hasattr(user, "availability") and user.availability:
            availability_slots = user.availability.slots or []
            if availability_slots:
                has_availability = True
                availability_by_day = format_availability_by_day(availability_slots)

        # Round previous average score if it exists
        prev_avg_score = response.annotated_previous_avg_score_value
        if prev_avg_score is not None:
            prev_avg_score = round(prev_avg_score, 1)

        # Get project preferences for this user/session
        project_preferences = [
            pref.project for pref in getattr(user, "prefetched_project_preferences", [])
        ]

        applicants.append(
            ApplicantData(
                user=user,
                response=response,
                score=response.score,
                selection_rank=response.selection_rank,
                current_team=current_team,
                current_role=current_role,
                previous_application_count=response.annotated_previous_application_count,
                previous_avg_score=prev_avg_score,
                has_availability=has_availability,
                availability_by_day=availability_by_day,
                project_preferences=project_preferences,
            )
        )

    return applicants, filterset


def get_teams_with_statistics(session: Session) -> list[TeamStatistics]:
    """
    Get all teams for a session with member details and availability statistics.

    Returns a list of TeamStatistics dataclass instances containing:
    - Team info
    - Navigators, captain, and djangonauts lists
    - Navigator meeting overlap hours
    - Captain 1-on-1 overlap hours with each djangonaut
    """
    teams = session.teams.all().prefetch_related(
        Prefetch(
            "session_memberships",
            queryset=SessionMembership.objects.filter(session=session)
            .select_related("user")
            .prefetch_related("user__availability"),
            to_attr="prefetched_all_members",
        )
    )

    teams_data = []
    for team in teams:
        # Separate members by role
        navigators = [
            m.user
            for m in team.prefetched_all_members
            if m.role == SessionMembership.NAVIGATOR
        ]
        captains = [
            m.user
            for m in team.prefetched_all_members
            if m.role == SessionMembership.CAPTAIN
        ]
        djangonauts = [
            m.user
            for m in team.prefetched_all_members
            if m.role == SessionMembership.DJANGONAUT
        ]

        captain = captains[0] if captains else None

        # Calculate availability statistics
        overlap_stats = calculate_team_overlap(navigators, captain, djangonauts)

        # Create a lookup dict for captain meeting hours by djangonaut id
        captain_hours_lookup = {}
        for meeting in overlap_stats.get("captain_meetings", []):
            captain_hours_lookup[meeting["djangonaut"].id] = meeting["hours"]

        # Get djangonaut details with scores/ranks and captain overlap hours
        djangonaut_details = []
        for djangonaut in djangonauts:
            # Get their application response
            try:
                response = UserSurveyResponse.objects.get(
                    user=djangonaut, survey=session.application_survey
                )
                djangonaut_details.append(
                    DjangonautDetail(
                        user=djangonaut,
                        score=response.score,
                        selection_rank=response.selection_rank,
                        captain_hours=captain_hours_lookup.get(djangonaut.id),
                    )
                )
            except UserSurveyResponse.DoesNotExist:
                djangonaut_details.append(
                    DjangonautDetail(
                        user=djangonaut,
                        score=None,
                        selection_rank=None,
                        captain_hours=captain_hours_lookup.get(djangonaut.id),
                    )
                )

        teams_data.append(
            TeamStatistics(
                team=team,
                navigators=navigators,
                captain=captain,
                djangonaut_details=djangonaut_details,
                navigator_meeting_hours=overlap_stats["navigator_meeting_hours"],
                captain_meetings=overlap_stats.get("captain_meetings", []),
                is_valid=overlap_stats["is_valid"],
            )
        )

    return teams_data
