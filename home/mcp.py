"""MCP tools mirroring the "Form Teams" admin workflow (home.views.team_formation).

Tools never return applicant emails or survey answer text; they link to the
admin instead. Every tool requires the ``home.form_team`` permission and is
scoped to sessions the caller organizes.
"""

from typing import Literal

import msgspec
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django_mcpz.bearer_tokens.auth import token_auth
from django_mcpz.oauth.auth import oauth_auth
from django_mcpz.server import MCPServer, ToolError

from accounts.models import CustomUser
from home.forms import BulkTeamAssignmentForm, BulkWaitlistForm, OverlapAnalysisForm
from home.models import Session, SessionMembership
from home.team_allocation import allocate_teams_bounded_search, apply_allocation
from home.views.team_formation import get_filtered_applicants, get_teams_with_statistics

FORM_TEAM_PERMISSION = "home.form_team"


def _bearer_token_or_oauth(request: HttpRequest):
    """Bearer token (Claude Code) or OAuth (ChatGPT, Claude.ai)."""
    if token_auth(request) is None:
        return None
    return oauth_auth(request)


server = MCPServer(
    name="djangonaut-space-team-formation",
    version="1.0.0",
    title="Djangonaut Space Team Formation",
    description=(
        "Filter applicants, compare availability, and form mentoring teams "
        "for a Djangonaut Space session."
    ),
    instructions=(
        "Use these tools to do everything the 'Form Teams' admin page does: "
        "list_sessions to find a session, list_applicants to filter/sort the "
        "applicant pool, list_teams to see current teams and their overlap "
        "statistics, check_availability_overlap to test a candidate against a "
        "team's navigators/captain before assigning them, assign_users_to_team "
        "and waitlist_users to act on that, and auto_allocate_teams to run the "
        "allocation algorithm. Tools never return an applicant's survey answer "
        "text directly; use the application_admin_url they return to open the "
        "full response in the admin when a human needs to read it."
    ),
    auth=_bearer_token_or_oauth,
)


def _display_name(user: CustomUser) -> str:
    """'First L.' - never the email address."""
    first_name = user.first_name.strip()
    last_initial = user.last_name.strip()[:1]
    if first_name and last_initial:
        return f"{first_name} {last_initial}."
    return first_name or user.username


def _project_preference_mismatch_message(
    session: Session, team, user_ids: list[int]
) -> str | None:
    """Rebuilds BulkTeamAssignmentForm's mismatch error without emails."""
    mismatched = CustomUser.objects.filter(
        id__in=user_ids
    ).with_invalid_project_preference(project=team.project, session=session)
    names = ", ".join(_display_name(user) for user in mismatched)
    if not names:
        return None
    return (
        f"The following applicants have not selected '{team.project.name}' as a "
        f"preference: {names}. Applicants with no preferences can be assigned to "
        "any project."
    )


def _absolute(request: HttpRequest, url: str) -> str:
    return request.build_absolute_uri(url)


def _get_session(request: HttpRequest, session_id: int) -> Session:
    return get_object_or_404(
        Session.objects.for_admin_site(request.user), pk=session_id
    )


def _form_errors(form) -> str:
    return "; ".join(
        f"{field}: {', '.join(errors)}" for field, errors in form.errors.items()
    )


class SessionIdParams(msgspec.Struct, forbid_unknown_fields=True):
    session_id: int


class SessionSummary(msgspec.Struct):
    id: int
    slug: str
    title: str
    status: str


class ListSessionsResult(msgspec.Struct):
    sessions: list[SessionSummary]


@server.tool(
    description=(
        "List the sessions (cohorts) this caller organizes, for choosing a "
        "session_id to pass to the other team-formation tools."
    ),
    read_only=True,
    permission=FORM_TEAM_PERMISSION,
)
def list_sessions(request: HttpRequest) -> ListSessionsResult:
    sessions = Session.objects.for_admin_site(request.user).order_by("-start_date")
    return ListSessionsResult(
        sessions=[
            SessionSummary(id=s.id, slug=s.slug, title=s.title, status=s.status)
            for s in sessions
        ]
    )


class ProjectSummary(msgspec.Struct):
    id: int
    name: str


class ApplicantSummary(msgspec.Struct):
    user_id: int
    name: str
    score: int | None
    selection_rank: int | None
    current_team_id: int | None
    current_team_name: str | None
    current_role: str | None
    is_waitlisted: bool
    previously_waitlisted: bool
    previous_application_count: int
    previous_avg_score: float | None
    tutorial_result: str | None
    has_availability: bool
    availability_by_day: dict[str, list[str]]
    project_preferences: list[ProjectSummary]
    application_admin_url: str


class ListApplicantsParams(msgspec.Struct, forbid_unknown_fields=True):
    session_id: int
    score_min: int | None = None
    score_max: int | None = None
    rank_min: int | None = None
    rank_max: int | None = None
    project_preference_id: int | None = None
    team_id: int | None = None
    show_unassigned_only: bool = False
    exclude_waitlisted: bool = False
    show_waitlisted_only: bool = False
    show_previously_waitlisted_only: bool = False
    sort_by: Literal[
        "score", "selection_rank", "annotated_previous_application_count"
    ] = "selection_rank"
    sort_order: Literal["asc", "desc"] = "asc"
    page: int = 1
    page_size: int = 25


class ListApplicantsResult(msgspec.Struct):
    applicants: list[ApplicantSummary]
    total_count: int
    page: int
    page_size: int
    total_pages: int


@server.tool(
    description=(
        "List applicants for a session's team formation, with the same "
        "filtering, sorting, and pagination as the 'Form Teams' admin page. "
        "Each applicant includes a link to their full survey response in the "
        "admin (application_admin_url) rather than the response content."
    ),
    read_only=True,
    permission=FORM_TEAM_PERMISSION,
)
def list_applicants(
    request: HttpRequest, params: ListApplicantsParams
) -> ListApplicantsResult:
    session = _get_session(request, params.session_id)

    if (
        params.team_id is not None
        and not session.teams.filter(pk=params.team_id).exists()
    ):
        raise ToolError(f"No team with id {params.team_id} in session {session.id}.")
    if (
        params.project_preference_id is not None
        and not session.available_projects.filter(
            pk=params.project_preference_id
        ).exists()
    ):
        raise ToolError(
            f"No project with id {params.project_preference_id} available for "
            f"session {session.id}."
        )

    filter_data = {}
    if params.score_min is not None:
        filter_data["score_min"] = params.score_min
    if params.score_max is not None:
        filter_data["score_max"] = params.score_max
    if params.rank_min is not None:
        filter_data["rank_min"] = params.rank_min
    if params.rank_max is not None:
        filter_data["rank_max"] = params.rank_max
    if params.project_preference_id is not None:
        filter_data["project_preferences"] = params.project_preference_id
    if params.team_id is not None:
        filter_data["team"] = params.team_id
    if params.show_unassigned_only:
        filter_data["show_unassigned_only"] = True
    if params.exclude_waitlisted:
        filter_data["exclude_waitlisted"] = True
    if params.show_waitlisted_only:
        filter_data["show_waitlisted_only"] = True
    if params.show_previously_waitlisted_only:
        filter_data["show_previously_waitlisted_only"] = True

    applicants, _filterset = get_filtered_applicants(
        session, filter_data, params.sort_by, params.sort_order
    )

    page_size = max(1, min(params.page_size, 100))
    paginator = Paginator(applicants, page_size)
    page_obj = paginator.get_page(params.page)

    summaries = [
        ApplicantSummary(
            user_id=applicant.user.id,
            name=_display_name(applicant.user),
            score=applicant.score,
            selection_rank=applicant.selection_rank,
            current_team_id=(
                applicant.current_team.id if applicant.current_team else None
            ),
            current_team_name=(
                applicant.current_team.name if applicant.current_team else None
            ),
            current_role=applicant.current_role,
            is_waitlisted=applicant.is_waitlisted,
            previously_waitlisted=applicant.previously_waitlisted,
            previous_application_count=applicant.previous_application_count,
            previous_avg_score=applicant.previous_avg_score,
            tutorial_result=applicant.tutorial_result,
            has_availability=applicant.has_availability,
            availability_by_day=applicant.availability_by_day,
            project_preferences=[
                ProjectSummary(id=project.id, name=project.name)
                for project in applicant.project_preferences
            ],
            application_admin_url=_absolute(
                request,
                reverse(
                    "admin:home_usersurveyresponse_change",
                    args=[applicant.response.id],
                ),
            ),
        )
        for applicant in page_obj.object_list
    ]

    return ListApplicantsResult(
        applicants=summaries,
        total_count=paginator.count,
        page=page_obj.number,
        page_size=page_size,
        total_pages=paginator.num_pages,
    )


class MemberSummary(msgspec.Struct):
    user_id: int
    name: str


class DjangonautSummary(msgspec.Struct):
    user_id: int
    name: str
    score: int | None
    selection_rank: int | None
    captain_overlap_hours: int | None


class TeamSummary(msgspec.Struct):
    id: int
    name: str
    project: str
    navigators: list[MemberSummary]
    captain: MemberSummary | None
    djangonauts: list[DjangonautSummary]
    navigator_meeting_hours: int
    is_valid: bool
    compare_availability_url: str


class ListTeamsResult(msgspec.Struct):
    teams: list[TeamSummary]
    min_navigator_meeting_hours: int
    min_captain_overlap_hours: int


@server.tool(
    description=(
        "List a session's current teams with their members and availability "
        "statistics: navigator meeting overlap hours, each djangonaut's "
        "1-on-1 overlap with the captain, and whether the team currently "
        "meets the minimum overlap requirements."
    ),
    read_only=True,
    permission=FORM_TEAM_PERMISSION,
)
def list_teams(request: HttpRequest, params: SessionIdParams) -> ListTeamsResult:
    session = _get_session(request, params.session_id)
    teams_data = get_teams_with_statistics(session)

    teams = [
        TeamSummary(
            id=stats.team.id,
            name=stats.team.name,
            project=stats.team.project.name,
            navigators=[
                MemberSummary(user_id=user.id, name=_display_name(user))
                for user in stats.navigators
            ],
            captain=(
                MemberSummary(
                    user_id=stats.captain.id, name=_display_name(stats.captain)
                )
                if stats.captain
                else None
            ),
            djangonauts=[
                DjangonautSummary(
                    user_id=detail.user.id,
                    name=_display_name(detail.user),
                    score=detail.score,
                    selection_rank=detail.selection_rank,
                    captain_overlap_hours=detail.captain_hours,
                )
                for detail in stats.djangonaut_details
            ],
            navigator_meeting_hours=stats.navigator_meeting_hours,
            is_valid=stats.is_valid,
            compare_availability_url=_absolute(request, stats.compare_availability_url),
        )
        for stats in teams_data
    ]

    return ListTeamsResult(
        teams=teams,
        min_navigator_meeting_hours=session.teams.model.MIN_NAVIGATOR_MEETING_HOURS,
        min_captain_overlap_hours=session.teams.model.MIN_CAPTAIN_OVERLAP_HOURS,
    )


class CheckOverlapParams(msgspec.Struct, forbid_unknown_fields=True):
    session_id: int
    team_id: int
    user_ids: list[int]
    analysis_type: Literal["navigator", "captain"] = "navigator"


class CandidateOverlap(msgspec.Struct):
    user_id: int
    name: str
    hour_blocks: int
    time_ranges: list[str]
    is_sufficient: bool
    compare_availability_url: str


class OverlapResult(msgspec.Struct):
    team_id: int
    analysis_type: Literal["navigator", "captain"]
    hour_blocks: int | None = None
    time_ranges: list[str] | None = None
    is_sufficient: bool | None = None
    compare_availability_url: str | None = None
    captain_id: int | None = None
    captain_name: str | None = None
    per_candidate: list[CandidateOverlap] | None = None


@server.tool(
    description=(
        "Check availability overlap before assigning candidates to a team, "
        "exactly like the overlap-analysis panel on the 'Form Teams' page. "
        "analysis_type='navigator' checks the team's navigators plus existing "
        "djangonauts against the given candidates together (needs the team's "
        "minimum navigator-meeting hours); 'captain' checks the team's "
        "captain against each candidate individually (needs the minimum "
        "captain-overlap hours)."
    ),
    read_only=True,
    permission=FORM_TEAM_PERMISSION,
)
def check_availability_overlap(
    request: HttpRequest, params: CheckOverlapParams
) -> OverlapResult:
    session = _get_session(request, params.session_id)
    prefix = OverlapAnalysisForm.prefix
    form = OverlapAnalysisForm(
        {
            f"{prefix}-team": params.team_id,
            f"{prefix}-analysis_type": f"overlap-{params.analysis_type}",
            f"{prefix}-user_ids": ",".join(str(uid) for uid in params.user_ids),
        },
        session=session,
    )
    if not form.is_valid():
        raise ToolError(_form_errors(form))

    try:
        context = form.get_overlap_context()
    except ValidationError as exc:
        raise ToolError("; ".join(exc.messages))

    if params.analysis_type == "navigator":
        return OverlapResult(
            team_id=params.team_id,
            analysis_type="navigator",
            hour_blocks=context["hour_blocks"],
            time_ranges=context["time_ranges"],
            is_sufficient=context["is_sufficient"],
            compare_availability_url=_absolute(
                request, context["compare_availability_url"]
            ),
        )

    captain = context["captain"]
    return OverlapResult(
        team_id=params.team_id,
        analysis_type="captain",
        captain_id=captain.id,
        captain_name=_display_name(captain),
        per_candidate=[
            CandidateOverlap(
                user_id=result["user"].id,
                name=_display_name(result["user"]),
                hour_blocks=result["hour_blocks"],
                time_ranges=result["time_ranges"],
                is_sufficient=result["is_sufficient"],
                compare_availability_url=_absolute(
                    request, result["compare_availability_url"]
                ),
            )
            for result in context["results"]
        ],
    )


class AssignTeamParams(msgspec.Struct, forbid_unknown_fields=True):
    session_id: int
    team_id: int
    user_ids: list[int]


class AssignTeamResult(msgspec.Struct):
    assigned_count: int
    team_id: int
    team_name: str


@server.tool(
    description=(
        "Assign applicants to a team for this session, exactly like the "
        "bulk-assign action on the 'Form Teams' page. Fails if any applicant "
        "has selected project preferences that do not include the team's "
        "project. Clears any waitlist entry for the assigned applicants."
    ),
    destructive=True,
    permission=FORM_TEAM_PERMISSION,
)
def assign_users_to_team(
    request: HttpRequest, params: AssignTeamParams
) -> AssignTeamResult:
    session = _get_session(request, params.session_id)
    prefix = BulkTeamAssignmentForm.prefix
    form = BulkTeamAssignmentForm(
        {
            f"{prefix}-team": params.team_id,
            f"{prefix}-user_ids": ",".join(str(uid) for uid in params.user_ids),
        },
        session=session,
    )
    if not form.is_valid():
        if "team" in form.errors:
            team = session.teams.filter(pk=params.team_id).first()
            if team is not None:
                message = _project_preference_mismatch_message(
                    session, team, params.user_ids
                )
                if message is not None:
                    raise ToolError(message)
        raise ToolError(_form_errors(form))

    assigned_count = form.save()
    team = form.cleaned_data["team"]
    return AssignTeamResult(
        assigned_count=assigned_count, team_id=team.id, team_name=team.name
    )


class WaitlistUsersParams(msgspec.Struct, forbid_unknown_fields=True):
    session_id: int
    user_ids: list[int]


class WaitlistUsersResult(msgspec.Struct):
    waitlisted_count: int
    removed_from_team_count: int


@server.tool(
    description=(
        "Add applicants to the session waitlist, exactly like the waitlist "
        "action on the 'Form Teams' page. Applicants who currently have a "
        "team assignment are removed from their team first."
    ),
    destructive=True,
    permission=FORM_TEAM_PERMISSION,
)
def waitlist_users(
    request: HttpRequest, params: WaitlistUsersParams
) -> WaitlistUsersResult:
    session = _get_session(request, params.session_id)
    prefix = BulkWaitlistForm.prefix
    form = BulkWaitlistForm(
        {
            f"{prefix}-user_ids": ",".join(str(uid) for uid in params.user_ids),
        },
        session=session,
    )
    if not form.is_valid():
        raise ToolError(_form_errors(form))

    removed_from_team_count = SessionMembership.objects.filter(
        session=session, user_id__in=form.cleaned_data["user_ids"]
    ).count()
    waitlisted_count = form.save()
    return WaitlistUsersResult(
        waitlisted_count=waitlisted_count,
        removed_from_team_count=removed_from_team_count,
    )


class AutoAllocateParams(msgspec.Struct, forbid_unknown_fields=True):
    session_id: int
    apply: bool = False


class RankPlacement(msgspec.Struct):
    selection_rank: int
    placed: int
    considered: int


class AutoAllocateResult(msgspec.Struct):
    applied: bool
    allocated_count: int
    complete_teams: int
    total_teams: int
    unallocated_user_ids: list[int]
    placements_by_rank: list[RankPlacement]


@server.tool(
    description=(
        "Run the bounded-search auto-allocation algorithm for a session, "
        "filling team slots one selection-rank tier at a time while "
        "respecting availability overlap and project preferences. With "
        "apply=false (the default) this only previews the outcome; pass "
        "apply=true to create the SessionMembership records, matching the "
        "'Auto-allocate Djangonauts to teams' admin action."
    ),
    destructive=True,
    permission=FORM_TEAM_PERMISSION,
)
def auto_allocate_teams(
    request: HttpRequest, params: AutoAllocateParams
) -> AutoAllocateResult:
    session = _get_session(request, params.session_id)
    allocation = allocate_teams_bounded_search(session)

    placements = [
        RankPlacement(
            selection_rank=rank,
            placed=placement.placed,
            considered=placement.considered,
        )
        for rank, placement in allocation.placements_by_rank.items()
    ]
    unallocated_user_ids = [
        candidate.user.id for candidate in allocation.unallocated_candidates
    ]

    if params.apply:
        stats = apply_allocation(allocation, session)
        return AutoAllocateResult(
            applied=True,
            allocated_count=stats["created"],
            complete_teams=stats["complete_teams"],
            total_teams=stats["total_teams"],
            unallocated_user_ids=unallocated_user_ids,
            placements_by_rank=placements,
        )

    return AutoAllocateResult(
        applied=False,
        allocated_count=len(allocation.allocated_candidates),
        complete_teams=sum(1 for team in allocation.teams if team.is_full),
        total_teams=len(allocation.teams),
        unallocated_user_ids=unallocated_user_ids,
        placements_by_rank=placements,
    )
