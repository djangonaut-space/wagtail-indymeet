"""
Team allocation algorithm for assigning Djangonauts to teams.

This module implements a bounded search algorithm that:
- Allocates Djangonauts to teams with Navigators and Captains already assigned
- Ensures availability overlap requirements are met:
  * 5+ hours overlap among ALL team members (navigators + all djangonauts)
  * 3+ hours overlap between captain and each individual djangonaut
- Respects project preferences
- Allocates one selection rank tier at a time (see ``SELECTION_RANK_TIERS``),
  so a tier only fills the slots the earlier tiers left open
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
from home import constants

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from copy import copy as shallow_copy
from dataclasses import dataclass, field
from functools import cached_property
from itertools import accumulate
from typing import TYPE_CHECKING, NamedTuple

from django.db.models import Prefetch

from home.availability import count_one_hour_block_values, get_user_slot_values
from home.models import SessionMembership, Team, UserSurveyResponse, ProjectPreference

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from home.models import Project, Session

# Selection ranks allocated together, best tier first. Each tier is only
# searched while teams still have open slots.
SELECTION_RANK_TIERS: tuple[tuple[int, ...], ...] = ((0, 1), (2,), (3,))


def _has_hours(slot_values: frozenset[float], min_hours: int) -> bool:
    """Whether the slots contain at least ``min_hours`` 1-hour blocks."""
    # Every hour block needs two slots, so small sets fail without sorting.
    if len(slot_values) < min_hours * 2:
        return False
    return count_one_hour_block_values(slot_values) >= min_hours


@dataclass
class AllocationCandidate:
    """Represents a Djangonaut candidate for team allocation."""

    user: CustomUser
    selection_rank: int
    score: int | None
    response: UserSurveyResponse
    project_preferences: list[Project]

    @cached_property
    def slot_values(self) -> frozenset[float]:
        """The candidate's UTC availability, computed once per search."""
        return get_user_slot_values(self.user)


@dataclass
class TeamSlot:
    """Represents a team with available slots for Djangonauts."""

    team: Team
    navigators: list[CustomUser]
    captain: CustomUser | None
    max_djangonauts: int = 3
    current_djangonauts: list[CustomUser] | None = None
    # The navigators' overlap, followed by the overlap after each Djangonaut
    # joined. None means the team has no members to overlap with yet.
    _meeting_slots_stack: list[frozenset[float] | None] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    def __post_init__(self):
        """Initialize current_djangonauts and the members' meeting overlap."""
        if self.current_djangonauts is None:
            self.current_djangonauts = []
        navigator_slots = [get_user_slot_values(user) for user in self.navigators]
        self._meeting_slots_stack = [
            frozenset.intersection(*navigator_slots) if navigator_slots else None
        ]
        for user in self.current_djangonauts:
            self._meeting_slots_stack.append(
                self._meeting_slots_with(get_user_slot_values(user))
            )

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
        return self.is_compatible(candidate) and self.can_fit(candidate)

    def is_compatible(self, candidate: AllocationCandidate) -> bool:
        """
        Check the constraints that don't depend on the team's current Djangonauts.

        Project preference and captain overlap never change while the team is
        being filled, so the search evaluates them once per candidate and team.
        """
        if not self._matches_project_preference(candidate):
            return False
        if self.captain and not self._has_sufficient_captain_overlap(candidate):
            return False
        return True

    def can_fit(self, candidate: AllocationCandidate) -> bool:
        """
        Check the constraints that depend on the team's current Djangonauts.

        Args:
            candidate: The candidate to check

        Returns:
            True if the team has room and keeps enough navigator meeting overlap
        """
        return not self.is_full and self._has_sufficient_navigator_overlap(candidate)

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

    def _meeting_slots_with(self, slot_values: frozenset[float]) -> frozenset[float]:
        """
        The team's meeting overlap if a member with ``slot_values`` joined.

        Args:
            slot_values: The joining member's UTC availability

        Returns:
            Slots shared by every navigator, current Djangonaut and the new member
        """
        meeting_slots = self._meeting_slots_stack[-1]
        if meeting_slots is None:
            return slot_values
        return meeting_slots & slot_values

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
        return _has_hours(
            self._meeting_slots_with(candidate.slot_values),
            Team.MIN_NAVIGATOR_MEETING_HOURS,
        )

    @cached_property
    def _captain_slot_values(self) -> frozenset[float]:
        """The captain's UTC availability, computed once per team slot."""
        return get_user_slot_values(self.captain)

    def _has_sufficient_captain_overlap(self, candidate: AllocationCandidate) -> bool:
        """
        Check if candidate has 3+ hours overlap with team captain.

        Args:
            candidate: The candidate to check

        Returns:
            True if overlap >= 3 hours, False otherwise
        """
        return _has_hours(
            self._captain_slot_values & candidate.slot_values,
            Team.MIN_CAPTAIN_OVERLAP_HOURS,
        )

    def add_djangonaut(self, candidate: AllocationCandidate) -> None:
        """
        Add a Djangonaut to this team.

        Args:
            candidate: The candidate to add
        """
        self._meeting_slots_stack.append(
            self._meeting_slots_with(candidate.slot_values)
        )
        self.current_djangonauts.append(candidate.user)

    def remove_last_djangonaut(self) -> None:
        """Remove the most recently added Djangonaut from this team."""
        if not self.current_djangonauts:
            return
        self.current_djangonauts.pop()
        self._meeting_slots_stack.pop()

    def copy(self) -> TeamSlot:
        """
        Create a copy of this TeamSlot that shares no mutable state with it.

        The meeting overlap stack is copied rather than rebuilt, so copying
        doesn't recompute anyone's availability.
        """
        team_slot = shallow_copy(self)
        team_slot.navigators = self.navigators[:]
        team_slot.current_djangonauts = self.current_djangonauts[:]
        team_slot._meeting_slots_stack = self._meeting_slots_stack[:]
        return team_slot


class RankPlacement(NamedTuple):
    """How many candidates of one selection rank were placed out of those considered."""

    placed: int
    considered: int


@dataclass
class AllocationState:
    """
    Represents the current state of team allocation.

    ``candidates`` holds every eligible applicant being allocated, placed or
    not, so the unplaced ones and per-rank placement counts are always derived
    from the current allocation rather than tracked separately.
    """

    teams: list[TeamSlot]
    allocated_candidates: list[tuple[AllocationCandidate, TeamSlot]]
    candidates: list[AllocationCandidate]

    @property
    def unallocated_candidates(self) -> list[AllocationCandidate]:
        """Candidates who weren't placed on a team, in priority order."""
        allocated_users = {
            candidate.user.id for candidate, _ in self.allocated_candidates
        }
        return [
            candidate
            for candidate in self.candidates
            if candidate.user.id not in allocated_users
        ]

    @property
    def placements_by_rank(self) -> dict[int, RankPlacement]:
        """
        Placed and considered candidate counts for each selection rank.

        A rank tier that was never searched because teams filled up still
        reports how many of its applicants were left out.

        Example:
            >>> allocation.placements_by_rank
            {0: RankPlacement(placed=12, considered=20), 3: RankPlacement(placed=2, considered=22)}
        """
        placed = Counter(
            candidate.selection_rank for candidate, _ in self.allocated_candidates
        )
        considered = Counter(candidate.selection_rank for candidate in self.candidates)
        return {
            rank: RankPlacement(placed=placed[rank], considered=considered[rank])
            for rank in sorted(considered)
        }

    def copy(self) -> AllocationState:
        """
        Create a deep copy of this allocation state.

        Allocated candidates are re-pointed at the copied team slots, so the
        copy shares no mutable TeamSlot with the original.
        """
        teams = [team.copy() for team in self.teams]
        teams_by_id = {team_slot.team.pk: team_slot for team_slot in teams}
        return AllocationState(
            teams=teams,
            allocated_candidates=[
                (candidate, teams_by_id[team_slot.team.pk])
                for candidate, team_slot in self.allocated_candidates
            ],
            candidates=self.candidates,
        )

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
        .select_related("user__availability")
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
            user__session_memberships__role=constants.DJANGONAUT,
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
    """
    Depth-first branch-and-bound search for the best allocation.

    Candidates are considered in priority order. A candidate who fits at least
    one team branches over every team they fit; a candidate who fits none is
    skipped. The search mutates one working state and backtracks, copying only
    when it finds a new best allocation.

    Subtrees are pruned when an optimistic bound on their score can't beat the
    best score found so far. Since an equal score never replaces the best state,
    pruning when ``bound <= best`` returns exactly what an exhaustive search of
    the same tree would.
    """

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
        self.state = initial_state.copy()
        self.best_state = initial_state.copy()
        self.best_score = self.best_state.get_score()
        self.compatible_teams = [
            [team for team in self.state.teams if team.is_compatible(candidate)]
            for candidate in candidates
        ]
        # min_rank_sums[i][k] is the smallest possible rank sum of k candidates
        # chosen from candidates[i:].
        self.min_rank_sums = [
            list(
                accumulate(
                    sorted(candidate.selection_rank for candidate in candidates[i:]),
                    initial=0,
                )
            )
            for i in range(len(candidates) + 1)
        ]

    def run(self) -> AllocationState:
        """Search every allocation and return the best one found."""
        rank_sum = sum(
            candidate.selection_rank for candidate, _ in self.state.allocated_candidates
        )
        self._search(0, rank_sum)
        return self.best_state

    def _search(self, candidate_index: int, rank_sum: int) -> None:
        """
        Recursive search to allocate candidates.

        Args:
            candidate_index: Index of next candidate to consider
            rank_sum: Sum of selection ranks of the allocated candidates
        """
        open_slots = [
            team.available_slots for team in self.state.teams if not team.is_full
        ]
        if candidate_index >= len(self.candidates) or not open_slots:
            self._record_leaf()
            return
        if not self._can_improve(candidate_index, rank_sum, open_slots):
            return

        candidate = self.candidates[candidate_index]

        allocated = False
        for team in self.compatible_teams[candidate_index]:
            if not team.can_fit(candidate):
                continue
            allocated = True
            with self._placed(candidate, team):
                # Look at the next candidate for this branch of teams
                self._search(candidate_index + 1, rank_sum + candidate.selection_rank)

        if not allocated:
            # If this particular candidate wasn't able to be assigned to
            # a team, move onto the next one regardless
            self._search(candidate_index + 1, rank_sum)

    @contextmanager
    def _placed(self, candidate: AllocationCandidate, team: TeamSlot) -> Iterator[None]:
        """
        Place a candidate on a team in the working state for the block.

        The placement is undone on exit, so every branch of the search leaves
        the working state as it found it.

        Args:
            candidate: The candidate to place
            team: The team to place them on
        """
        team.add_djangonaut(candidate)
        self.state.allocated_candidates.append((candidate, team))
        try:
            yield
        finally:
            self.state.allocated_candidates.pop()
            team.remove_last_djangonaut()

    def _record_leaf(self) -> None:
        """Keep the working state if it beats the best allocation so far."""
        score = self.state.get_score()
        if score > self.best_score:
            self.best_score = score
            self.best_state = self.state.copy()

    def _can_improve(
        self, candidate_index: int, rank_sum: int, open_slots: list[int]
    ) -> bool:
        """
        Whether the subtree below the working state could beat the best score.

        Scores compare as (allocated, complete teams, -rank sum). At most
        ``placeable`` more candidates can be allocated. If that total differs
        from the best allocation count, it alone decides. On a tie, only
        branches that place all ``placeable`` candidates can compete, so their
        complete teams are bounded by filling the teams needing the fewest
        Djangonauts first, and their rank sum by the best remaining ranks.

        Args:
            candidate_index: Index of next candidate to consider
            rank_sum: Sum of selection ranks of the allocated candidates
            open_slots: Available slots of each team that isn't full

        Returns:
            False if no allocation in this subtree can score higher than best
        """
        best_allocated, best_complete, best_negative_rank_sum = self.best_score
        placeable = min(len(self.candidates) - candidate_index, sum(open_slots))
        max_allocated = len(self.state.allocated_candidates) + placeable
        if max_allocated != best_allocated:
            return max_allocated > best_allocated

        fillable_teams = 0
        unplaced = placeable
        for needed in sorted(open_slots):
            if needed > unplaced:
                break
            unplaced -= needed
            fillable_teams += 1
        max_complete = len(self.state.teams) - len(open_slots) + fillable_teams
        max_negative_rank_sum = -(
            rank_sum + self.min_rank_sums[candidate_index][placeable]
        )
        return (max_complete, max_negative_rank_sum) > (
            best_complete,
            best_negative_rank_sum,
        )


def allocate_teams_bounded_search(session: Session) -> AllocationState:
    """
    Allocate Djangonauts to teams using bounded search, one rank tier at a time.

    The tiers in ``SELECTION_RANK_TIERS`` are searched in order while teams
    have open slots. Each tier searches for the best placement of its own
    candidates on top of the earlier tiers' result, so a lower tier never
    displaces a higher-ranked candidate, even when doing so would fill more
    slots.

    Uses a decision tree with branch-and-bound to explore allocation possibilities.
    Prunes branches that cannot improve on the current best solution.

    Args:
        session: The session to allocate teams for

    Returns:
        Best AllocationState found
    """
    state = AllocationState(
        teams=get_team_slots(session),
        allocated_candidates=[],
        candidates=get_allocation_candidates(
            session, max_rank=max(SELECTION_RANK_TIERS[-1])
        ),
    )

    for tier in SELECTION_RANK_TIERS:
        if all(team.is_full for team in state.teams):
            break
        tier_candidates = [
            candidate
            for candidate in state.unallocated_candidates
            if candidate.selection_rank in tier
        ]
        if tier_candidates:
            state = _TeamAllocationSearcher(tier_candidates, state).run()

    return state


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
            role=constants.DJANGONAUT,
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
