"""
Team allocation algorithm for assigning Djangonauts to teams.

This module implements a bounded search algorithm that:
- Allocates Djangonauts to teams with Navigators and Captains already assigned
- Ensures availability overlap requirements are met:
  * 5+ hours overlap among ALL team members (navigators + all djangonauts)
  * 3+ hours overlap between captain and each individual djangonaut
- Respects project preferences
- Optimizes for allocating the highest-ranked applicants
- Prefers forming complete teams of 3 Djangonauts

IMPORTANT - Cumulative Overlap Constraint:
    The 5-hour navigator overlap requirement applies to ALL members of the team
    together. As each djangonaut is added, the common overlapping time window
    may shrink. The algorithm checks that adding a new djangonaut maintains at
    least 5 hours of overlap across ALL navigators and ALL djangonauts (both
    existing and new).

    Example:
        Navigator: Mon 00:00-06:00
        Add Django1 (Mon 00:00-06:00) → Overlap = 6 hours ✓
        Add Django2 (Mon 00:00-05:00) → Overlap (nav+d1+d2) = 5 hours ✓
        Try Django3 (Mon 00:00-04:00) → Overlap (nav+d1+d2+d3) = 4 hours ✗
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import Prefetch

from home.availability import calculate_overlap
from home.models import SessionMembership, Team, UserSurveyResponse, ProjectPreference

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from home.models import Project, Session


@dataclass
class AllocationCandidate:
    """Represents a Djangonaut candidate for team allocation."""

    user: CustomUser
    selection_rank: int
    score: int | None
    response: UserSurveyResponse
    project_preferences: list[Project]


@dataclass
class TeamSlot:
    """Represents a team with available slots for Djangonauts."""

    team: Team
    navigators: list[CustomUser]
    captain: CustomUser | None
    max_djangonauts: int = 3
    current_djangonauts: list[CustomUser] | None = None

    def __post_init__(self):
        """Initialize current_djangonauts list if not provided."""
        if self.current_djangonauts is None:
            self.current_djangonauts = []

    @property
    def available_slots(self) -> int:
        """Get number of available slots on this team."""
        return self.max_djangonauts - len(self.current_djangonauts)

    @property
    def is_full(self) -> bool:
        """Check if team has reached maximum Djangonauts."""
        return len(self.current_djangonauts) >= self.max_djangonauts

    def can_add_djangonaut(self, candidate: AllocationCandidate) -> bool:
        """
        Check if a candidate can be added to this team.

        Validates:
        - Team has available slots
        - Navigator availability overlap (5+ hours)
        - Captain availability overlap (3+ hours)
        - Project preferences match

        Args:
            candidate: The candidate to check

        Returns:
            True if candidate can be added, False otherwise
        """
        if self.is_full:
            return False
        if not self._matches_project_preference(candidate):
            return False
        if not self._has_sufficient_navigator_overlap(candidate):
            return False
        if self.captain and not self._has_sufficient_captain_overlap(candidate):
            return False
        return True

    def _matches_project_preference(self, candidate: AllocationCandidate) -> bool:
        """
        Check if candidate's project preferences match this team's project.

        If candidate has no preferences, they match any project.
        If candidate has preferences, team's project must be in their list.

        Args:
            candidate: The candidate to check

        Returns:
            True if preferences match, False otherwise
        """
        if not candidate.project_preferences:
            return True

        return self.team.project in candidate.project_preferences

    def _has_sufficient_navigator_overlap(self, candidate: AllocationCandidate) -> bool:
        """
        Check if adding candidate maintains 5+ hours overlap for entire team.

        This checks that ALL navigators + ALL current djangonauts + new candidate
        have at least 5 hours of overlapping availability. This ensures the whole
        team can meet together for navigator meetings.

        Args:
            candidate: The candidate to check

        Returns:
            True if overlap >= 5 hours, False otherwise
        """
        all_participants = self.navigators + self.current_djangonauts + [candidate.user]
        _, hours = calculate_overlap(all_participants)
        return hours >= Team.MIN_NAVIGATOR_MEETING_HOURS

    def _has_sufficient_captain_overlap(self, candidate: AllocationCandidate) -> bool:
        """
        Check if candidate has 3+ hours overlap with team captain.

        Args:
            candidate: The candidate to check

        Returns:
            True if overlap >= 3 hours, False otherwise
        """
        _, hours = calculate_overlap([self.captain, candidate.user])
        return hours >= Team.MIN_CAPTAIN_OVERLAP_HOURS

    def add_djangonaut(self, candidate: AllocationCandidate) -> None:
        """
        Add a Djangonaut to this team.

        Args:
            candidate: The candidate to add
        """
        self.current_djangonauts.append(candidate.user)

    def remove_last_djangonaut(self) -> None:
        """Remove the most recently added Djangonaut from this team."""
        if self.current_djangonauts:
            self.current_djangonauts.pop()

    def copy(self) -> TeamSlot:
        """Create a deep copy of this TeamSlot."""
        return TeamSlot(
            team=self.team,
            navigators=self.navigators[:],
            captain=self.captain,
            max_djangonauts=self.max_djangonauts,
            current_djangonauts=self.current_djangonauts[:],
        )


@dataclass
class AllocationState:
    """Represents the current state of team allocation."""

    teams: list[TeamSlot]
    allocated_candidates: list[tuple[AllocationCandidate, TeamSlot]]
    unallocated_candidates: list[AllocationCandidate]

    def copy(self) -> AllocationState:
        """Create a deep copy of this allocation state."""
        return AllocationState(
            teams=[team.copy() for team in self.teams],
            allocated_candidates=self.allocated_candidates[:],
            unallocated_candidates=self.unallocated_candidates[:],
        )

    def add_candidate(
        self, team_slot: TeamSlot, candidate: AllocationCandidate
    ) -> AllocationState:
        new_state = self.copy()
        team = next(
            _slot for _slot in new_state.teams if _slot.team.id == team_slot.team.id
        )
        team.add_djangonaut(candidate)
        new_state.allocated_candidates.append((candidate, team))
        return new_state

    def get_score(self) -> tuple[int, int, int]:
        """
        Calculate a score for this allocation state.

        Returns tuple of (num_allocated, num_complete_teams, sum_of_ranks).
        Higher is better for comparisons. We use negative sum_of_ranks because
        lower selection_rank values are better.

        Returns:
            Tuple of (number allocated, number of complete teams, negative sum of ranks)
        """
        num_allocated = len(self.allocated_candidates)
        num_complete_teams = sum(1 for team in self.teams if team.is_full)

        sum_of_ranks = sum(
            candidate.selection_rank for candidate, _ in self.allocated_candidates
        )

        return (num_allocated, num_complete_teams, -sum_of_ranks)


def get_allocation_candidates(
    session: Session, max_rank: int
) -> list[AllocationCandidate]:
    """
    Get all eligible candidates for team allocation.

    Filters to:
    - Users who applied to the session
    - Not already assigned to a team
    - Have selection_rank <= max_rank (lower is better, 0=best)

    Sorted by:
    - selection_rank ASC (lower is better)
    - score DESC (higher is better)

    Args:
        session: The session to get candidates for
        max_rank: Maximum selection rank to include

    Returns:
        List of AllocationCandidate instances sorted by priority
    """
    if not session.application_survey_id:
        return []

    responses = (
        UserSurveyResponse.objects.filter(survey=session.application_survey)
        .select_related("user")
        .prefetch_related(
            Prefetch(
                "user__project_preferences",
                queryset=ProjectPreference.objects.for_session(session).select_related(
                    "project"
                ),
                to_attr="prefetched_project_preferences",
            )
        )
        .exclude(
            user__session_memberships__session=session,
            user__session_memberships__role=SessionMembership.DJANGONAUT,
        )
        .filter(
            selection_rank__lte=max_rank,
        )
        .order_by("selection_rank", "-score")
    )

    candidates = []
    for response in responses:
        candidates.append(
            AllocationCandidate(
                user=response.user,
                selection_rank=response.selection_rank,
                score=response.score,
                response=response,
                project_preferences=[
                    pref.project
                    for pref in response.user.prefetched_project_preferences
                ],
            )
        )

    return candidates


def get_team_slots(session: Session) -> list[TeamSlot]:
    """
    Get all teams with available slots for Djangonauts.

    Args:
        session: The session to get teams for

    Returns:
        List of TeamSlot instances representing teams with capacity
    """
    teams = session.teams.all()

    team_slots = []
    for team in teams:
        navigators = [
            membership.user
            for membership in team.session_memberships.navigators().select_related(
                "user__availability"
            )
        ]

        captain = (
            team.session_memberships.captains()
            .select_related("user__availability")
            .first()
        )
        if captain:
            captain = captain.user

        current_djangonauts = [
            membership.user
            for membership in team.session_memberships.djangonauts().select_related(
                "user__availability"
            )
        ]

        if len(current_djangonauts) < 3:
            team_slots.append(
                TeamSlot(
                    team=team,
                    navigators=navigators,
                    captain=captain,
                    max_djangonauts=3,
                    current_djangonauts=current_djangonauts,
                )
            )

    return team_slots


class _TeamAllocationSearcher:
    """Helper class for searching for the best session member allocations."""

    def __init__(
        self, candidates: list[AllocationCandidate], initial_state: AllocationState
    ):
        """
        Initialize the searcher.

        Args:
            candidates: List of candidates to allocate
            initial_state: Initial allocation state
        """
        self.candidates = candidates
        self.best_state = initial_state.copy()
        self.best_score = self.best_state.get_score()

    def search(self, state: AllocationState, candidate_index: int) -> None:
        """
        Recursive search to allocate candidates.

        Args:
            state: Current allocation state
            candidate_index: Index of next candidate to consider
        """
        if candidate_index >= len(self.candidates):
            current_score = state.get_score()
            if current_score > self.best_score:
                self.best_score = current_score
                self.best_state = state.copy()
            return

        candidate = self.candidates[candidate_index]

        allocated = False
        for team in state.teams:
            if not team.can_add_djangonaut(candidate):
                continue
            allocated = True
            new_state = state.add_candidate(team, candidate)
            # Look at the next candidate for this branch of teams
            self.search(new_state, candidate_index + 1)

        if not allocated:
            # If this particular candidate wasn't able to be assigned to
            # a team, move onto the next one regardless
            self.search(state, candidate_index + 1)


def allocate_teams_bounded_search(session: Session) -> AllocationState:
    """
    Allocate Djangonauts to teams using bounded search with two-phase allocation.

    Phase 1: Allocates candidates with selection_rank 0-2
    Phase 2: If teams are not full, allocates candidates with selection_rank 3

    Uses a decision tree with branch-and-bound to explore allocation possibilities.
    Prunes branches that cannot improve on the current best solution.

    Args:
        session: The session to allocate teams for

    Returns:
        Best AllocationState found
    """
    # Phase 1: Try to fill teams with candidates ranked 0-2
    candidates = get_allocation_candidates(session, max_rank=2)
    teams = get_team_slots(session)

    initial_state = AllocationState(
        teams=teams, allocated_candidates=[], unallocated_candidates=candidates
    )
    if not candidates or not teams:
        return initial_state

    # Run phase 1 search
    searcher = _TeamAllocationSearcher(candidates, initial_state)
    searcher.search(initial_state, 0)
    best_state = searcher.best_state

    # Phase 2: If any teams still have space, try rank 3 candidates
    has_available_slots = any(team.available_slots > 0 for team in best_state.teams)

    if has_available_slots:
        # Get rank 3 candidates (not already allocated in phase 1)
        rank3_candidates = get_allocation_candidates(session, max_rank=3)

        # Filter out candidates already allocated in phase 1
        allocated_users = {
            candidate.user.id for candidate, _ in best_state.allocated_candidates
        }
        rank3_only = [
            c
            for c in rank3_candidates
            if c.user.id not in allocated_users and c.selection_rank == 3
        ]

        if rank3_only:
            # Start phase 2 with the state from phase 1
            phase2_initial = AllocationState(
                teams=[team.copy() for team in best_state.teams],
                allocated_candidates=list(best_state.allocated_candidates),
                unallocated_candidates=rank3_only,
            )

            # Run phase 2 search
            phase2_searcher = _TeamAllocationSearcher(rank3_only, phase2_initial)
            phase2_searcher.search(phase2_initial, 0)
            best_state = phase2_searcher.best_state

    return best_state


def apply_allocation(allocation: AllocationState, session: Session) -> dict[str, int]:
    """
    Apply an allocation state to the database.

    Creates SessionMembership records for allocated Djangonauts.

    Args:
        allocation: The allocation state to apply
        session: The session to apply allocations to

    Returns:
        Dictionary with statistics about the allocation
    """
    members = [
        SessionMembership(
            user=candidate.user,
            session=session,
            team=team_slot.team,
            role=SessionMembership.DJANGONAUT,
        )
        for candidate, team_slot in allocation.allocated_candidates
    ]
    SessionMembership.objects.bulk_create(
        members,
        ignore_conflicts=True,
    )
    return {
        "created": len(members),
        "complete_teams": sum(1 for team in allocation.teams if team.is_full),
        "total_teams": len(allocation.teams),
    }
