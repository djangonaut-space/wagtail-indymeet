"""Tests for team allocation algorithm."""

import random
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
import time_machine

from accounts.factories import UserAvailabilityFactory, UserFactory
from home import constants
from home.factories import ProjectFactory, TeamFactory
from home.models import (
    Project,
    ProjectPreference,
    Session,
    SessionMembership,
    Survey,
    Team,
    UserSurveyResponse,
)
from tests.timezones import CENTRAL_EUROPEAN_TIMEZONE, US_EASTERN_TIMEZONE
from home.slots import Slot
from home.team_allocation import (
    AllocationCandidate,
    AllocationState,
    TeamSlot,
    _TeamAllocationSearcher,
    allocate_teams_bounded_search,
    apply_allocation,
    get_allocation_candidates,
    get_team_slots,
)


class TeamSlotTestCase(TestCase):
    """Test TeamSlot dataclass functionality."""

    def setUp(self):
        """Create test data."""
        self.session = Session.objects.create(
            title="Test Session",
            slug="test-session",
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )
        self.project = ProjectFactory(name="Test Project")
        self.team = TeamFactory(session=self.session, project=self.project)

        # Create navigator with availability
        self.navigator = UserFactory(username="nav1", email="nav1@test.com")
        UserAvailabilityFactory(
            user=self.navigator,
            slots=[24.0 + (i * 0.5) for i in range(12)],  # Mon 00:00-06:00 (6 hours)
        )
        SessionMembership.objects.create(
            user=self.navigator,
            session=self.session,
            team=self.team,
            role=constants.NAVIGATOR,
        )

        # Create captain with availability
        self.captain = UserFactory(username="captain1", email="captain1@test.com")
        UserAvailabilityFactory(
            user=self.captain,
            slots=[24.0 + (i * 0.5) for i in range(10)],  # Mon 00:00-05:00 (5 hours)
        )
        SessionMembership.objects.create(
            user=self.captain,
            session=self.session,
            team=self.team,
            role=constants.CAPTAIN,
        )

        self.team_slot = TeamSlot(
            team=self.team,
            navigators=[self.navigator],
            captain=self.captain,
            max_djangonauts=3,
        )

    def test_available_slots(self):
        """Test calculating available slots."""
        self.assertEqual(self.team_slot.available_slots, 3)

        # Add a djangonaut
        user = UserFactory()
        candidate = AllocationCandidate(
            user=user, selection_rank=2, score=10, response=None, project_preferences=[]
        )
        self.team_slot.add_djangonaut(candidate)

        self.assertEqual(self.team_slot.available_slots, 2)

    def test_is_full(self):
        """Test checking if team is full."""
        self.assertFalse(self.team_slot.is_full)

        # Add 3 djangonauts
        for i in range(3):
            user = UserFactory(username=f"user{i}")
            candidate = AllocationCandidate(
                user=user,
                selection_rank=2,
                score=10,
                response=None,
                project_preferences=[],
            )
            self.team_slot.add_djangonaut(candidate)

        self.assertTrue(self.team_slot.is_full)

    def test_matches_project_preference_no_preferences(self):
        """Test candidate with no preferences matches any project."""
        user = UserFactory()
        candidate = AllocationCandidate(
            user=user,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[],  # No preferences
        )

        self.assertTrue(self.team_slot._matches_project_preference(candidate))

    def test_matches_project_preference_with_match(self):
        """Test candidate with matching preference."""
        user = UserFactory()
        candidate = AllocationCandidate(
            user=user,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[self.project],  # Matches team's project
        )

        self.assertTrue(self.team_slot._matches_project_preference(candidate))

    def test_matches_project_preference_no_match(self):
        """Test candidate with non-matching preference."""
        user = UserFactory()
        other_project = ProjectFactory(name="Other Project")
        candidate = AllocationCandidate(
            user=user,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[other_project],  # Does not match team's project
        )

        self.assertFalse(self.team_slot._matches_project_preference(candidate))

    def test_has_sufficient_navigator_overlap(self):
        """Test checking navigator overlap."""
        # Create user with sufficient overlap (5+ hours)
        user = UserFactory()
        UserAvailabilityFactory(
            user=user,
            slots=[24.0 + (i * 0.5) for i in range(10)],  # Mon 00:00-05:00 (5 hours)
        )
        candidate = AllocationCandidate(
            user=user, selection_rank=2, score=10, response=None, project_preferences=[]
        )

        self.assertTrue(self.team_slot._has_sufficient_navigator_overlap(candidate))

        # Create user with insufficient overlap
        user2 = UserFactory()
        UserAvailabilityFactory(
            user=user2,
            slots=[24.0 + (i * 0.5) for i in range(6)],  # Mon 00:00-03:00 (3 hours)
        )
        candidate2 = AllocationCandidate(
            user=user2,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[],
        )

        self.assertFalse(self.team_slot._has_sufficient_navigator_overlap(candidate2))

    @time_machine.travel("2024-06-17", tick=False)
    def test_navigator_overlap_uses_user_timezones(self):
        """Navigator overlap compares derived UTC slots across timezones."""
        navigator = UserFactory(username="timezone_nav")
        UserAvailabilityFactory(
            user=navigator,
            slots=[33.0 + (i * 0.5) for i in range(10)],
            slots_timezone=US_EASTERN_TIMEZONE,
        )
        team_slot = TeamSlot(
            team=self.team,
            navigators=[navigator],
            captain=None,
        )

        user = UserFactory(username="timezone_candidate")
        UserAvailabilityFactory(
            user=user,
            slots=[39.0 + (i * 0.5) for i in range(10)],
            slots_timezone=CENTRAL_EUROPEAN_TIMEZONE,
        )
        candidate = AllocationCandidate(
            user=user,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[],
        )

        self.assertTrue(team_slot._has_sufficient_navigator_overlap(candidate))

    def test_navigator_overlap_with_existing_djangonauts(self):
        """Test that navigator overlap check includes existing djangonauts on the team."""
        # Add first djangonaut to team with Mon 00:00-05:00 availability
        django1 = UserFactory(username="django1")
        UserAvailabilityFactory(
            user=django1,
            slots=[24.0 + (i * 0.5) for i in range(10)],  # Mon 00:00-05:00
        )
        candidate1 = AllocationCandidate(
            user=django1,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[],
        )
        self.team_slot.add_djangonaut(candidate1)

        # Now try to add second djangonaut with Mon 00:00-04:00 availability
        # Navigator has Mon 00:00-06:00
        # The overlap between navigator + django1 + django2 should be Mon 00:00-04:00 (4 hours)
        # which is < 5 hours, so this should fail
        django2 = UserFactory(username="django2")
        UserAvailabilityFactory(
            user=django2,
            slots=[24.0 + (i * 0.5) for i in range(8)],  # Mon 00:00-04:00 (4 hours)
        )
        candidate2 = AllocationCandidate(
            user=django2,
            selection_rank=3,
            score=9,
            response=None,
            project_preferences=[],
        )

        # This should fail because the combined overlap is only 4 hours
        self.assertFalse(self.team_slot._has_sufficient_navigator_overlap(candidate2))

        # But if django2 has Mon 00:00-05:00+ availability, it should work
        django3 = UserFactory(username="django3")
        UserAvailabilityFactory(
            user=django3,
            slots=[24.0 + (i * 0.5) for i in range(10)],  # Mon 00:00-05:00 (5 hours)
        )
        candidate3 = AllocationCandidate(
            user=django3,
            selection_rank=4,
            score=8,
            response=None,
            project_preferences=[],
        )

        # This should succeed because the combined overlap is 5 hours
        self.assertTrue(self.team_slot._has_sufficient_navigator_overlap(candidate3))

    def test_has_sufficient_captain_overlap(self):
        """Test checking captain overlap."""
        # Create user with sufficient overlap (3+ hours)
        user = UserFactory()
        UserAvailabilityFactory(
            user=user,
            slots=[24.0 + (i * 0.5) for i in range(6)],  # Mon 00:00-03:00 (3 hours)
        )
        candidate = AllocationCandidate(
            user=user, selection_rank=2, score=10, response=None, project_preferences=[]
        )

        self.assertTrue(self.team_slot._has_sufficient_captain_overlap(candidate))

        # Create user with insufficient overlap
        user2 = UserFactory()
        UserAvailabilityFactory(
            user=user2,
            slots=[24.0 + (i * 0.5) for i in range(4)],  # Mon 00:00-02:00 (2 hours)
        )
        candidate2 = AllocationCandidate(
            user=user2,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[],
        )

        self.assertFalse(self.team_slot._has_sufficient_captain_overlap(candidate2))

    @time_machine.travel("2024-06-17", tick=False)
    def test_captain_overlap_uses_user_timezones(self):
        """Captain overlap compares derived UTC slots across timezones."""
        captain = UserFactory(username="timezone_captain")
        UserAvailabilityFactory(
            user=captain,
            slots=[33.0 + (i * 0.5) for i in range(6)],
            slots_timezone=US_EASTERN_TIMEZONE,
        )
        team_slot = TeamSlot(
            team=self.team,
            navigators=[self.navigator],
            captain=captain,
        )

        user = UserFactory(username="timezone_captain_candidate")
        UserAvailabilityFactory(
            user=user,
            slots=[39.0 + (i * 0.5) for i in range(6)],
            slots_timezone=CENTRAL_EUROPEAN_TIMEZONE,
        )
        candidate = AllocationCandidate(
            user=user,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[],
        )

        self.assertTrue(team_slot._has_sufficient_captain_overlap(candidate))

    def test_can_add_djangonaut(self):
        """Test checking if a candidate can be added."""
        # Create valid candidate
        user = UserFactory()
        UserAvailabilityFactory(
            user=user,
            slots=[24.0 + (i * 0.5) for i in range(10)],  # Mon 00:00-05:00
        )
        candidate = AllocationCandidate(
            user=user,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[],
        )

        self.assertTrue(self.team_slot.can_add_djangonaut(candidate))

        # Fill the team
        for i in range(3):
            u = UserFactory(username=f"filler{i}")
            UserAvailabilityFactory(
                user=u,
                slots=[24.0 + (i * 0.5) for i in range(10)],
            )
            c = AllocationCandidate(
                user=u,
                selection_rank=2,
                score=10,
                response=None,
                project_preferences=[],
            )
            self.team_slot.add_djangonaut(c)

        # Team is full now
        self.assertFalse(self.team_slot.can_add_djangonaut(candidate))

    def test_can_add_djangonaut_fails_captain_overlap(self):
        """
        Test that candidate is rejected when captain overlap is insufficient.

        Sets up a scenario where:
        - Navigator has Mon 00:00-06:00
        - Captain has Tue 00:00-05:00 (different day)
        - Candidate has Mon 00:00-05:00 + Tue 00:00-02:00

        Result: Candidate passes navigator check (5 hours) but fails captain check (2 hours < 3).
        """
        candidate_user = UserFactory()
        UserAvailabilityFactory(
            user=candidate_user,
            slots=(
                [24.0 + (i * 0.5) for i in range(10)]
                + [48.0 + (i * 0.5) for i in range(4)]
            ),
        )

        captain_with_different_schedule = UserFactory(
            username="captain2", email="captain2@test.com"
        )
        UserAvailabilityFactory(
            user=captain_with_different_schedule,
            slots=[48.0 + (i * 0.5) for i in range(10)],
        )

        team_slot = TeamSlot(
            team=self.team,
            navigators=[self.navigator],
            captain=captain_with_different_schedule,
            max_djangonauts=3,
        )

        candidate = AllocationCandidate(
            user=candidate_user,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[],
        )

        self.assertFalse(team_slot.can_add_djangonaut(candidate))

    def test_remove_last_djangonaut(self):
        """Test removing the last djangonaut from a team."""
        user1 = UserFactory(username="user1")
        candidate1 = AllocationCandidate(
            user=user1,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[],
        )
        self.team_slot.add_djangonaut(candidate1)

        user2 = UserFactory(username="user2")
        candidate2 = AllocationCandidate(
            user=user2, selection_rank=3, score=9, response=None, project_preferences=[]
        )
        self.team_slot.add_djangonaut(candidate2)

        self.assertEqual(len(self.team_slot.current_djangonauts), 2)
        self.assertEqual(self.team_slot.available_slots, 1)

        self.team_slot.remove_last_djangonaut()

        self.assertEqual(len(self.team_slot.current_djangonauts), 1)
        self.assertEqual(self.team_slot.available_slots, 2)
        self.assertEqual(self.team_slot.current_djangonauts[0], user1)

    def test_remove_last_djangonaut_empty(self):
        """Test removing from empty team does nothing."""
        self.assertEqual(len(self.team_slot.current_djangonauts), 0)
        self.team_slot.remove_last_djangonaut()
        self.assertEqual(len(self.team_slot.current_djangonauts), 0)

    def test_remove_restores_overlap(self):
        """Removing a Djangonaut restores the meeting overlap it had narrowed."""
        early = UserFactory(username="early")
        UserAvailabilityFactory(
            user=early,
            slots=[24.0 + (i * 0.5) for i in range(10)],  # Mon 00:00-05:00
        )
        early_candidate = AllocationCandidate(
            user=early,
            selection_rank=0,
            score=10,
            response=None,
            project_preferences=[],
        )
        late = UserFactory(username="late")
        UserAvailabilityFactory(
            user=late,
            slots=[25.0 + (i * 0.5) for i in range(10)],  # Mon 01:00-06:00
        )
        late_candidate = AllocationCandidate(
            user=late, selection_rank=0, score=10, response=None, project_preferences=[]
        )

        self.assertTrue(self.team_slot.can_add_djangonaut(late_candidate))
        self.team_slot.add_djangonaut(early_candidate)
        self.assertFalse(self.team_slot.can_add_djangonaut(late_candidate))
        self.team_slot.remove_last_djangonaut()
        self.assertTrue(self.team_slot.can_add_djangonaut(late_candidate))

    def test_existing_djangonauts_overlap(self):
        """
        Djangonauts a slot starts with narrow the overlap and can be removed.

        Also checks a copy keeps that overlap history.
        """
        early = UserFactory(username="early")
        UserAvailabilityFactory(
            user=early,
            slots=[24.0 + (i * 0.5) for i in range(10)],  # Mon 00:00-05:00
        )
        late = UserFactory(username="late")
        UserAvailabilityFactory(
            user=late,
            slots=[25.0 + (i * 0.5) for i in range(10)],  # Mon 01:00-06:00
        )
        late_candidate = AllocationCandidate(
            user=late, selection_rank=0, score=10, response=None, project_preferences=[]
        )
        team_slot = TeamSlot(
            team=self.team,
            navigators=[self.navigator],
            captain=None,
            current_djangonauts=[early],
        ).copy()

        self.assertFalse(team_slot.can_add_djangonaut(late_candidate))
        team_slot.remove_last_djangonaut()
        self.assertTrue(team_slot.can_add_djangonaut(late_candidate))


class GetAllocationCandidatesTestCase(TestCase):
    """Test get_allocation_candidates function."""

    def setUp(self):
        """Create test data."""
        self.session = Session.objects.create(
            title="Test Session",
            slug="test-session",
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )
        self.survey = Survey.objects.create(
            name="Application Survey", session=self.session
        )
        self.session.application_survey = self.survey
        self.session.save()

    def test_no_survey(self):
        """Test when session has no application survey."""
        session = Session.objects.create(
            title="No Survey Session",
            slug="no-survey",
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )

        candidates = get_allocation_candidates(session, max_rank=2)
        self.assertEqual(len(candidates), 0)

    def test_filters_already_assigned(self):
        """Test that already assigned users are excluded."""
        user = UserFactory()
        UserSurveyResponse.objects.create(
            user=user, survey=self.survey, selection_rank=2, score=10
        )

        # Assign user to a team
        team = TeamFactory(session=self.session)
        SessionMembership.objects.create(
            user=user,
            session=self.session,
            team=team,
            role=constants.DJANGONAUT,
        )

        candidates = get_allocation_candidates(self.session, max_rank=2)
        self.assertEqual(len(candidates), 0)

    def test_filters_high_selection_rank(self):
        """Test that selection_rank > 2 are excluded (lower is better)."""
        user1 = UserFactory(username="user1")
        UserSurveyResponse.objects.create(
            user=user1, survey=self.survey, selection_rank=0, score=10
        )

        user2 = UserFactory(username="user2")
        UserSurveyResponse.objects.create(
            user=user2, survey=self.survey, selection_rank=1, score=10
        )

        user3 = UserFactory(username="user3")
        UserSurveyResponse.objects.create(
            user=user3, survey=self.survey, selection_rank=2, score=10
        )

        user4 = UserFactory(username="user4")
        UserSurveyResponse.objects.create(
            user=user4, survey=self.survey, selection_rank=3, score=10
        )

        candidates = get_allocation_candidates(self.session, max_rank=2)
        self.assertEqual(len(candidates), 3)
        candidate_users = [c.user for c in candidates]
        self.assertIn(user1, candidate_users)
        self.assertIn(user2, candidate_users)
        self.assertIn(user3, candidate_users)
        self.assertNotIn(user4, candidate_users)

    def test_sorting(self):
        """Test that candidates are sorted by selection_rank ASC, score DESC."""
        user1 = UserFactory(username="user1")
        UserSurveyResponse.objects.create(
            user=user1, survey=self.survey, selection_rank=1, score=5
        )

        user2 = UserFactory(username="user2")
        UserSurveyResponse.objects.create(
            user=user2, survey=self.survey, selection_rank=0, score=8
        )

        user3 = UserFactory(username="user3")
        UserSurveyResponse.objects.create(
            user=user3, survey=self.survey, selection_rank=0, score=10
        )

        candidates = get_allocation_candidates(self.session, max_rank=2)
        self.assertEqual(len(candidates), 3)

        self.assertEqual(candidates[0].user, user3)
        self.assertEqual(candidates[1].user, user2)
        self.assertEqual(candidates[2].user, user1)

    def test_includes_project_preferences(self):
        """Test that project preferences are included."""
        user = UserFactory()
        response = UserSurveyResponse.objects.create(
            user=user, survey=self.survey, selection_rank=2, score=10
        )

        project1 = ProjectFactory(name="Project 1")
        project2 = ProjectFactory(name="Project 2")
        ProjectPreference.objects.create(
            user=user, session=self.session, project=project1
        )
        ProjectPreference.objects.create(
            user=user, session=self.session, project=project2
        )

        candidates = get_allocation_candidates(self.session, max_rank=2)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(candidates[0].project_preferences), 2)
        self.assertIn(project1, candidates[0].project_preferences)
        self.assertIn(project2, candidates[0].project_preferences)


class GetTeamSlotsTestCase(TestCase):
    """Test get_team_slots function."""

    def setUp(self):
        """Create test data."""
        self.session = Session.objects.create(
            title="Test Session",
            slug="test-session",
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )

    def test_empty_session(self):
        """Test session with no teams."""
        team_slots = get_team_slots(self.session)
        self.assertEqual(len(team_slots), 0)

    def test_excludes_full_teams(self):
        """Test that teams with 3 Djangonauts are excluded."""
        team = TeamFactory(session=self.session)
        navigator = UserFactory(username="nav")
        SessionMembership.objects.create(
            user=navigator,
            session=self.session,
            team=team,
            role=constants.NAVIGATOR,
        )

        # Add 3 Djangonauts
        for i in range(3):
            user = UserFactory(username=f"django{i}")
            SessionMembership.objects.create(
                user=user,
                session=self.session,
                team=team,
                role=constants.DJANGONAUT,
            )

        team_slots = get_team_slots(self.session)
        self.assertEqual(len(team_slots), 0)

    def test_includes_partial_teams(self):
        """Test that teams with < 3 Djangonauts are included."""
        team = TeamFactory(session=self.session)
        navigator = UserFactory(username="nav")
        SessionMembership.objects.create(
            user=navigator,
            session=self.session,
            team=team,
            role=constants.NAVIGATOR,
        )

        # Add 1 Djangonaut
        user = UserFactory(username="django1")
        SessionMembership.objects.create(
            user=user,
            session=self.session,
            team=team,
            role=constants.DJANGONAUT,
        )

        team_slots = get_team_slots(self.session)
        self.assertEqual(len(team_slots), 1)
        self.assertEqual(team_slots[0].available_slots, 2)

    def test_includes_navigators_and_captain(self):
        """Test that navigators and captain are included."""
        team = TeamFactory(session=self.session)

        nav1 = UserFactory(username="nav1")
        nav2 = UserFactory(username="nav2")
        captain = UserFactory(username="captain")

        SessionMembership.objects.create(
            user=nav1, session=self.session, team=team, role=constants.NAVIGATOR
        )
        SessionMembership.objects.create(
            user=nav2, session=self.session, team=team, role=constants.NAVIGATOR
        )
        SessionMembership.objects.create(
            user=captain,
            session=self.session,
            team=team,
            role=constants.CAPTAIN,
        )

        team_slots = get_team_slots(self.session)
        self.assertEqual(len(team_slots), 1)
        self.assertEqual(len(team_slots[0].navigators), 2)
        self.assertEqual(team_slots[0].captain, captain)


class AllocationStateTestCase(TestCase):
    """Test AllocationState dataclass."""

    def test_get_score(self):
        """Test calculating allocation score."""
        # Create mock data
        team = TeamFactory()
        team_slot = TeamSlot(team=team, navigators=[], captain=None)

        user1 = UserFactory(username="user1")
        candidate1 = AllocationCandidate(
            user=user1,
            selection_rank=2,
            score=10,
            response=None,
            project_preferences=[],
        )

        user2 = UserFactory(username="user2")
        candidate2 = AllocationCandidate(
            user=user2, selection_rank=3, score=8, response=None, project_preferences=[]
        )

        # Add candidates to team
        team_slot.add_djangonaut(candidate1)
        team_slot.add_djangonaut(candidate2)

        state = AllocationState(
            teams=[team_slot],
            allocated_candidates=[(candidate1, team_slot), (candidate2, team_slot)],
            candidates=[candidate1, candidate2],
        )

        score = state.get_score()
        # (num_allocated=2, num_complete=0, -sum_of_ranks=-(2+3)=-5)
        self.assertEqual(score, (2, 0, -5))

        # Add third candidate to make team complete
        user3 = UserFactory(username="user3")
        candidate3 = AllocationCandidate(
            user=user3, selection_rank=4, score=7, response=None, project_preferences=[]
        )
        team_slot.add_djangonaut(candidate3)
        state.allocated_candidates.append((candidate3, team_slot))

        score = state.get_score()
        # (num_allocated=3, num_complete=1, -sum_of_ranks=-(2+3+4)=-9)
        self.assertEqual(score, (3, 1, -9))

    def test_copy_repoints_teams(self):
        """Allocated candidates in a copy reference the copied TeamSlots."""
        team_slot = TeamSlot(team=TeamFactory(), navigators=[], captain=None)
        candidate = AllocationCandidate(
            user=UserFactory(),
            selection_rank=0,
            score=10,
            response=None,
            project_preferences=[],
        )
        team_slot.add_djangonaut(candidate)
        state = AllocationState(
            teams=[team_slot],
            allocated_candidates=[(candidate, team_slot)],
            candidates=[candidate],
        )

        copied = state.copy()

        self.assertIsNot(copied.teams[0], team_slot)
        self.assertIs(copied.allocated_candidates[0][1], copied.teams[0])

    def test_placements_by_rank(self):
        """Counts placed candidates per rank out of all candidates."""
        team_slot = TeamSlot(team=TeamFactory(), navigators=[], captain=None)
        placed, skipped_rank_zero, skipped_rank_two = (
            AllocationCandidate(
                user=UserFactory(),
                selection_rank=rank,
                score=10,
                response=None,
                project_preferences=[],
            )
            for rank in (0, 0, 2)
        )
        state = AllocationState(
            teams=[team_slot],
            allocated_candidates=[(placed, team_slot)],
            candidates=[placed, skipped_rank_zero, skipped_rank_two],
        )

        self.assertEqual(state.placements_by_rank, {0: (1, 2), 2: (0, 1)})
        self.assertEqual(
            state.unallocated_candidates, [skipped_rank_zero, skipped_rank_two]
        )


def _availability_user(user_id: int, start: float, length: int) -> SimpleNamespace:
    """An unsaved stand-in user available for ``length`` UTC slots from ``start``."""
    slots = [Slot("UTC", start + (i * 0.5)) for i in range(length)]
    return SimpleNamespace(
        id=user_id, availability=SimpleNamespace(get_slots=lambda: slots)
    )


def _exhaustive_allocation(
    candidates: list[AllocationCandidate], initial_state: AllocationState
) -> AllocationState:
    """
    Walk the same tree as _TeamAllocationSearcher, without pruning.

    A candidate who fits any team is placed on each fitting team in turn, and
    a candidate who fits none is skipped. The first strictly best leaf wins.
    """
    state = initial_state.copy()
    best = state.copy()

    def walk(index: int) -> None:
        nonlocal best
        if index == len(candidates):
            if state.get_score() > best.get_score():
                best = state.copy()
            return
        candidate = candidates[index]
        fitting_teams = [
            team for team in state.teams if team.can_add_djangonaut(candidate)
        ]
        for team in fitting_teams:
            team.add_djangonaut(candidate)
            state.allocated_candidates.append((candidate, team))
            walk(index + 1)
            state.allocated_candidates.pop()
            team.remove_last_djangonaut()
        if not fitting_teams:
            walk(index + 1)

    walk(0)
    return best


class TeamAllocationSearcherTestCase(SimpleTestCase):
    """Test the branch-and-bound search against an exhaustive search."""

    def _random_allocation_inputs(
        self, rng: random.Random
    ) -> tuple[list[AllocationCandidate], AllocationState]:
        """Build a small random session with mixed constraints and ranks."""
        projects = ["django", "wagtail"]
        teams = []
        for pk in range(3):
            captain = (
                _availability_user(
                    -100 - pk, 24.0 + rng.randint(0, 8) * 0.5, rng.randint(8, 14)
                )
                if rng.random() < 0.5
                else None
            )
            existing = (
                [_availability_user(-200 - pk, 24.0, rng.randint(10, 16))]
                if rng.random() < 0.3
                else []
            )
            teams.append(
                TeamSlot(
                    team=SimpleNamespace(pk=pk, project=projects[pk % 2]),
                    navigators=[
                        _availability_user(
                            -pk - 1, 24.0 + rng.randint(0, 4) * 0.5, rng.randint(12, 16)
                        )
                    ],
                    captain=captain,
                    current_djangonauts=existing,
                )
            )
        candidates = [
            AllocationCandidate(
                user=_availability_user(
                    user_id, 24.0 + rng.randint(0, 8) * 0.5, rng.randint(8, 16)
                ),
                selection_rank=rng.randint(0, 3),
                score=None,
                response=None,
                project_preferences=rng.choice([[], [projects[0]], [projects[1]]]),
            )
            for user_id in range(7)
        ]
        state = AllocationState(
            teams=teams, allocated_candidates=[], candidates=candidates
        )
        return candidates, state

    def test_matches_exhaustive_search(self):
        """
        Pruning never changes the chosen allocation.

        Compares team assignments on random inputs, so a pruning bound that
        cuts off a better allocation fails here even if other tests pass.
        """
        for seed in range(40):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                candidates, state = self._random_allocation_inputs(rng)

                expected = _exhaustive_allocation(candidates, state)
                actual = _TeamAllocationSearcher(candidates, state).run()

                self.assertEqual(
                    [
                        (candidate.user.id, team.team.pk)
                        for candidate, team in actual.allocated_candidates
                    ],
                    [
                        (candidate.user.id, team.team.pk)
                        for candidate, team in expected.allocated_candidates
                    ],
                )


class AllocateTeamsBoundedSearchTestCase(TestCase):
    """Test the main allocation algorithm."""

    def setUp(self):
        """Create test data."""
        self.session = Session.objects.create(
            title="Test Session",
            slug="test-session",
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )
        self.survey = Survey.objects.create(
            name="Application Survey", session=self.session
        )
        self.session.application_survey = self.survey
        self.session.save()

        # Create a project
        self.project = ProjectFactory(name="Django")

        # Create team with navigator and captain
        self.team = TeamFactory(session=self.session, project=self.project)

        self.navigator = UserFactory(username="navigator")
        UserAvailabilityFactory(
            user=self.navigator,
            slots=[24.0 + (i * 0.5) for i in range(12)],  # Mon 00:00-06:00
        )
        SessionMembership.objects.create(
            user=self.navigator,
            session=self.session,
            team=self.team,
            role=constants.NAVIGATOR,
        )

        self.captain = UserFactory(username="captain")
        UserAvailabilityFactory(
            user=self.captain,
            slots=[24.0 + (i * 0.5) for i in range(10)],  # Mon 00:00-05:00
        )
        SessionMembership.objects.create(
            user=self.captain,
            session=self.session,
            team=self.team,
            role=constants.CAPTAIN,
        )

    def test_no_candidates(self):
        """Test allocation with no candidates."""
        allocation = allocate_teams_bounded_search(self.session)
        self.assertEqual(len(allocation.allocated_candidates), 0)

    def test_no_teams(self):
        """Test allocation with no teams."""
        # Remove the team
        self.team.delete()

        # Create a candidate
        user = UserFactory()
        UserSurveyResponse.objects.create(
            user=user, survey=self.survey, selection_rank=2, score=10
        )

        allocation = allocate_teams_bounded_search(self.session)
        self.assertEqual(len(allocation.allocated_candidates), 0)

    def test_basic_allocation(self):
        """Test basic allocation with compatible candidates."""
        candidates = []
        for i in range(3):
            user = UserFactory(username=f"applicant{i}")
            UserAvailabilityFactory(
                user=user,
                slots=[24.0 + (j * 0.5) for j in range(10)],
            )
            UserSurveyResponse.objects.create(
                user=user, survey=self.survey, selection_rank=i, score=10 - i
            )
            candidates.append(user)

        allocation = allocate_teams_bounded_search(self.session)
        self.assertEqual(len(allocation.allocated_candidates), 3)

        allocated_users = [c.user for c, _ in allocation.allocated_candidates]
        self.assertEqual(allocated_users[0], candidates[0])
        self.assertEqual(allocated_users[1], candidates[1])
        self.assertEqual(allocated_users[2], candidates[2])

    def test_respects_availability_constraints(self):
        """Test that candidates without sufficient overlap are not allocated."""
        user1 = UserFactory(username="applicant1")
        UserAvailabilityFactory(
            user=user1,
            slots=[24.0 + (i * 0.5) for i in range(6)],
        )
        UserSurveyResponse.objects.create(
            user=user1, survey=self.survey, selection_rank=0, score=10
        )

        user2 = UserFactory(username="applicant2")
        UserAvailabilityFactory(
            user=user2,
            slots=[24.0 + (i * 0.5) for i in range(10)],
        )
        UserSurveyResponse.objects.create(
            user=user2, survey=self.survey, selection_rank=1, score=9
        )

        allocation = allocate_teams_bounded_search(self.session)
        self.assertEqual(len(allocation.allocated_candidates), 1)
        self.assertEqual(allocation.allocated_candidates[0][0].user, user2)

    def test_respects_project_preferences(self):
        """Test that project preferences are respected."""
        other_project = ProjectFactory(name="Wagtail")

        user1 = UserFactory(username="applicant1")
        UserAvailabilityFactory(
            user=user1,
            slots=[24.0 + (i * 0.5) for i in range(10)],
        )
        UserSurveyResponse.objects.create(
            user=user1, survey=self.survey, selection_rank=0, score=10
        )
        ProjectPreference.objects.create(
            user=user1, session=self.session, project=other_project
        )

        user2 = UserFactory(username="applicant2")
        UserAvailabilityFactory(
            user=user2,
            slots=[24.0 + (i * 0.5) for i in range(10)],
        )
        UserSurveyResponse.objects.create(
            user=user2, survey=self.survey, selection_rank=1, score=9
        )
        ProjectPreference.objects.create(
            user=user2, session=self.session, project=self.project
        )

        allocation = allocate_teams_bounded_search(self.session)
        self.assertEqual(len(allocation.allocated_candidates), 1)
        self.assertEqual(allocation.allocated_candidates[0][0].user, user2)

    def test_prefers_higher_ranked_candidates(self):
        """Test that higher-ranked candidates are preferred (lower rank number is better)."""
        candidates = []
        for i in range(5):
            user = UserFactory(username=f"applicant{i}")
            UserAvailabilityFactory(
                user=user,
                slots=[24.0 + (j * 0.5) for j in range(10)],
            )
            UserSurveyResponse.objects.create(
                user=user, survey=self.survey, selection_rank=i, score=10
            )
            candidates.append(user)

        allocation = allocate_teams_bounded_search(self.session)
        self.assertEqual(len(allocation.allocated_candidates), 3)

        allocated_users = [c.user for c, _ in allocation.allocated_candidates]
        self.assertIn(candidates[0], allocated_users)
        self.assertIn(candidates[1], allocated_users)
        self.assertIn(candidates[2], allocated_users)
        self.assertNotIn(candidates[3], allocated_users)
        self.assertNotIn(candidates[4], allocated_users)
        # Rank 4 is never eligible; rank 3 counts even though teams filled first.
        self.assertEqual(
            allocation.placements_by_rank,
            {0: (1, 1), 1: (1, 1), 2: (1, 1), 3: (0, 1)},
        )

    def test_diminishing_overlap_with_multiple_djangonauts(self):
        """Test that algorithm respects diminishing overlap as more djangonauts are added."""
        user1 = UserFactory(username="applicant1")
        UserAvailabilityFactory(
            user=user1,
            slots=[24.0 + (i * 0.5) for i in range(12)],
        )
        UserSurveyResponse.objects.create(
            user=user1, survey=self.survey, selection_rank=0, score=10
        )

        user2 = UserFactory(username="applicant2")
        UserAvailabilityFactory(
            user=user2,
            slots=[24.0 + (i * 0.5) for i in range(10)],
        )
        UserSurveyResponse.objects.create(
            user=user2, survey=self.survey, selection_rank=1, score=9
        )

        user3 = UserFactory(username="applicant3")
        UserAvailabilityFactory(
            user=user3,
            slots=[24.0 + (i * 0.5) for i in range(8)],
        )
        UserSurveyResponse.objects.create(
            user=user3, survey=self.survey, selection_rank=2, score=8
        )

        allocation = allocate_teams_bounded_search(self.session)

        self.assertEqual(len(allocation.allocated_candidates), 2)
        allocated_users = [c.user for c, _ in allocation.allocated_candidates]
        self.assertIn(user1, allocated_users)
        self.assertIn(user2, allocated_users)
        self.assertNotIn(user3, allocated_users)

    def test_phase2_allocation_with_rank3_candidates(self):
        """
        Test that rank 3 candidates are allocated when teams have space.

        The allocation algorithm works in rank tiers:
        - Tier 1: Allocates candidates with selection_rank 0-1
        - Tier 2: If teams still have slots, allocates candidates with selection_rank 2
        - Tier 3: If teams still have slots, allocates candidates with selection_rank 3

        This test verifies that:
        1. Tier 1 allocates rank 0-1 candidates (user1, user2) filling 2 of 3 team slots
        2. Tier 3 detects remaining capacity and allocates rank 3 candidate (user3)
        3. All 3 candidates end up allocated across the tiers
        """
        user1 = UserFactory(username="applicant1")
        UserAvailabilityFactory(
            user=user1,
            slots=[24.0 + (i * 0.5) for i in range(10)],
        )
        UserSurveyResponse.objects.create(
            user=user1, survey=self.survey, selection_rank=0, score=10
        )

        user2 = UserFactory(username="applicant2")
        UserAvailabilityFactory(
            user=user2,
            slots=[24.0 + (i * 0.5) for i in range(10)],
        )
        UserSurveyResponse.objects.create(
            user=user2, survey=self.survey, selection_rank=1, score=9
        )

        user3 = UserFactory(username="applicant3")
        UserAvailabilityFactory(
            user=user3,
            slots=[24.0 + (i * 0.5) for i in range(10)],
        )
        UserSurveyResponse.objects.create(
            user=user3, survey=self.survey, selection_rank=3, score=8
        )

        allocation = allocate_teams_bounded_search(self.session)

        self.assertEqual(len(allocation.allocated_candidates), 3)
        allocated_users = [c.user for c, _ in allocation.allocated_candidates]
        self.assertIn(user1, allocated_users)
        self.assertIn(user2, allocated_users)
        self.assertIn(user3, allocated_users)

    def test_backtracks_for_more_allocations(self):
        """
        The search looks past the first team a candidate fits.

        The top candidate fits both teams, but placing them on the first team
        (the first branch explored) leaves no room for three candidates who
        only fit that team. The best allocation puts them on the second team.
        """
        second_team = TeamFactory(session=self.session, project=self.project)
        second_navigator = UserFactory(username="second_navigator")
        UserAvailabilityFactory(
            user=second_navigator,
            slots=[48.0 + (i * 0.5) for i in range(12)],  # Tue 00:00-06:00
        )
        SessionMembership.objects.create(
            user=second_navigator,
            session=self.session,
            team=second_team,
            role=constants.NAVIGATOR,
        )

        flexible = UserFactory(username="flexible")
        UserAvailabilityFactory(
            user=flexible,
            slots=[day + (i * 0.5) for day in (24.0, 48.0) for i in range(10)],
        )
        UserSurveyResponse.objects.create(
            user=flexible, survey=self.survey, selection_rank=0, score=10
        )
        for i in range(3):
            user = UserFactory(username=f"monday{i}")
            UserAvailabilityFactory(
                user=user,
                slots=[24.0 + (j * 0.5) for j in range(10)],  # Mon 00:00-05:00
            )
            UserSurveyResponse.objects.create(
                user=user, survey=self.survey, selection_rank=1, score=9 - i
            )

        allocation = allocate_teams_bounded_search(self.session)

        self.assertEqual(len(allocation.allocated_candidates), 4)
        teams_by_user = {
            candidate.user: team_slot.team
            for candidate, team_slot in allocation.allocated_candidates
        }
        self.assertEqual(teams_by_user[flexible], second_team)

    def test_rank_one_beats_more_rank_two(self):
        """
        Ranks 0-1 are placed before rank 2 is considered.

        Searched together, putting the rank 0 candidate on the second team
        would leave room for both rank 2 candidates (3 allocated). Rank 1 goes
        first instead: rank 0 joins the first team so rank 1 can join the
        second, and neither rank 2 candidate fits alongside rank 0 afterwards.
        """
        second_team = TeamFactory(session=self.session, project=self.project)
        second_navigator = UserFactory(username="second_navigator")
        UserAvailabilityFactory(
            user=second_navigator,
            slots=[48.0 + (i * 0.5) for i in range(12)],  # Tue 00:00-06:00
        )
        SessionMembership.objects.create(
            user=second_navigator,
            session=self.session,
            team=second_team,
            role=constants.NAVIGATOR,
        )

        rank_zero = UserFactory(username="rank_zero")
        UserAvailabilityFactory(
            user=rank_zero,
            # Mon and Tue 00:00-05:00
            slots=[day + (i * 0.5) for day in (24.0, 48.0) for i in range(10)],
        )
        UserSurveyResponse.objects.create(
            user=rank_zero, survey=self.survey, selection_rank=0, score=10
        )
        rank_one = UserFactory(username="rank_one")
        UserAvailabilityFactory(
            user=rank_one,
            slots=[49.0 + (i * 0.5) for i in range(10)],  # Tue 01:00-06:00
        )
        UserSurveyResponse.objects.create(
            user=rank_one, survey=self.survey, selection_rank=1, score=10
        )
        rank_twos = []
        for i in range(2):
            user = UserFactory(username=f"rank_two{i}")
            UserAvailabilityFactory(
                user=user,
                slots=[25.0 + (j * 0.5) for j in range(10)],  # Mon 01:00-06:00
            )
            UserSurveyResponse.objects.create(
                user=user, survey=self.survey, selection_rank=2, score=10 - i
            )
            rank_twos.append(user)

        allocation = allocate_teams_bounded_search(self.session)

        teams_by_user = {
            candidate.user: team_slot.team
            for candidate, team_slot in allocation.allocated_candidates
        }
        self.assertEqual(teams_by_user, {rank_zero: self.team, rank_one: second_team})

    def test_admin_action_message(self):
        """The admin action reports placements out of candidates per rank."""
        for i in range(2):
            user = UserFactory(username=f"rank_zero{i}")
            UserAvailabilityFactory(
                user=user,
                slots=[24.0 + (j * 0.5) for j in range(10)],  # Mon 00:00-05:00
            )
            UserSurveyResponse.objects.create(
                user=user, survey=self.survey, selection_rank=0, score=10 - i
            )
        unavailable = UserFactory(username="unavailable")
        UserSurveyResponse.objects.create(
            user=unavailable, survey=self.survey, selection_rank=3, score=10
        )
        self.client.force_login(
            UserFactory(username="admin", is_staff=True, is_superuser=True)
        )

        response = self.client.post(
            reverse("admin:home_session_changelist"),
            {
                "action": "auto_allocate_teams_action",
                "_selected_action": [self.session.pk],
            },
            follow=True,
        )

        self.assertContains(
            response, "Placed by selection rank: rank 0: 2 of 2, rank 3: 0 of 1."
        )


class ApplyAllocationTestCase(TestCase):
    """Test applying allocation to database."""

    def setUp(self):
        """Create test data."""
        self.session = Session.objects.create(
            title="Test Session",
            slug="test-session",
            start_date="2025-06-01",
            end_date="2025-12-31",
            invitation_date="2025-01-01",
            application_start_date="2025-01-15",
            application_end_date="2025-02-15",
        )
        self.survey = Survey.objects.create(
            name="Application Survey", session=self.session
        )
        self.session.application_survey = self.survey
        self.session.save()

        self.team = TeamFactory(session=self.session)

    def test_creates_memberships(self):
        """Test that SessionMembership records are created."""
        team_slot = TeamSlot(team=self.team, navigators=[], captain=None)

        user1 = UserFactory(username="user1")
        response1 = UserSurveyResponse.objects.create(
            user=user1, survey=self.survey, selection_rank=2, score=10
        )
        candidate1 = AllocationCandidate(
            user=user1,
            selection_rank=2,
            score=10,
            response=response1,
            project_preferences=[],
        )

        user2 = UserFactory(username="user2")
        response2 = UserSurveyResponse.objects.create(
            user=user2, survey=self.survey, selection_rank=3, score=9
        )
        candidate2 = AllocationCandidate(
            user=user2,
            selection_rank=3,
            score=9,
            response=response2,
            project_preferences=[],
        )

        allocation = AllocationState(
            teams=[team_slot],
            allocated_candidates=[(candidate1, team_slot), (candidate2, team_slot)],
            candidates=[candidate1, candidate2],
        )

        stats = apply_allocation(allocation, self.session)

        self.assertEqual(stats["created"], 2)
        self.assertEqual(
            SessionMembership.objects.filter(
                session=self.session, role=constants.DJANGONAUT
            ).count(),
            2,
        )

        # Verify the memberships
        membership1 = SessionMembership.objects.get(user=user1)
        self.assertEqual(membership1.team, self.team)
        self.assertEqual(membership1.role, constants.DJANGONAUT)

        membership2 = SessionMembership.objects.get(user=user2)
        self.assertEqual(membership2.team, self.team)
        self.assertEqual(membership2.role, constants.DJANGONAUT)

    def test_returns_statistics(self):
        """Test that statistics are returned correctly."""
        team_slot = TeamSlot(team=self.team, navigators=[], captain=None)

        # Add 3 candidates to make team complete
        candidates = []
        for i in range(3):
            user = UserFactory(username=f"user{i}")
            response = UserSurveyResponse.objects.create(
                user=user, survey=self.survey, selection_rank=2 + i, score=10
            )
            candidate = AllocationCandidate(
                user=user,
                selection_rank=2 + i,
                score=10,
                response=response,
                project_preferences=[],
            )
            candidates.append((candidate, team_slot))
            team_slot.add_djangonaut(candidate)

        allocation = AllocationState(
            teams=[team_slot],
            allocated_candidates=candidates,
            candidates=[candidate for candidate, _ in candidates],
        )

        stats = apply_allocation(allocation, self.session)

        self.assertEqual(stats["created"], 3)
        self.assertEqual(stats["complete_teams"], 1)
        self.assertEqual(stats["total_teams"], 1)
