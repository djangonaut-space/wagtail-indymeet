"""Tests for CustomUser queryset managers and methods."""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from accounts.factories import UserAvailabilityFactory, UserFactory
from accounts.models import CustomUser
from home.factories import (
    OrganizerFactory,
    ProjectFactory,
    SessionFactory,
    SessionMembershipFactory,
)
from home.models import ProjectPreference, SessionMembership, Team


class CustomUserQuerySetTestCase(TestCase):
    """Test CustomUser queryset methods."""

    def setUp(self):
        """Create test data."""
        self.session = SessionFactory()
        self.project1 = ProjectFactory(name="Django")
        self.project2 = ProjectFactory(name="Wagtail")

        # Add projects to session
        self.session.available_projects.add(self.project1, self.project2)

        # Create users
        self.user1 = UserFactory(username="user1")
        self.user2 = UserFactory(username="user2")
        self.user3 = UserFactory(username="user3")
        self.user4 = UserFactory(username="user4")

        # user1: prefers project1
        ProjectPreference.objects.create(
            user=self.user1, session=self.session, project=self.project1
        )

        # user2: prefers project2
        ProjectPreference.objects.create(
            user=self.user2, session=self.session, project=self.project2
        )

        # user3: prefers both projects
        ProjectPreference.objects.create(
            user=self.user3, session=self.session, project=self.project1
        )
        ProjectPreference.objects.create(
            user=self.user3, session=self.session, project=self.project2
        )

        # user4: no preferences

    def test_with_project_preference(self):
        """Test filtering users who have selected a specific project preference."""
        users = CustomUser.objects.with_project_preference(
            project=self.project1, session=self.session
        )

        # user1 and user3 prefer project1
        self.assertEqual(users.count(), 2)
        self.assertIn(self.user1, users)
        self.assertIn(self.user3, users)
        self.assertNotIn(self.user2, users)
        self.assertNotIn(self.user4, users)

    def test_with_project_preference_no_matches(self):
        """Test with_project_preference returns empty queryset when no users match."""
        # Create a project not preferred by anyone
        project3 = ProjectFactory(name="Flask")
        users = CustomUser.objects.with_project_preference(
            project=project3, session=self.session
        )

        self.assertEqual(users.count(), 0)

    def test_with_invalid_project_preference(self):
        """Test filtering users with conflicting project preferences."""
        users = CustomUser.objects.with_invalid_project_preference(
            project=self.project1, session=self.session
        )

        # user2 has preferences for this session but not for project1
        # user1 and user3 prefer project1, so they're excluded
        # user4 has NO preferences at all, so they're excluded too(can be assigned anywhere)
        self.assertEqual(users.count(), 1)
        self.assertIn(self.user2, users)
        self.assertNotIn(self.user1, users)
        self.assertNotIn(self.user3, users)
        self.assertNotIn(self.user4, users)

    def test_with_invalid_project_preference_excludes_users_with_no_preferences(self):
        """
        Test that users with no preferences at all are excluded
        (they can be assigned anywhere).
        """
        users = CustomUser.objects.with_invalid_project_preference(
            project=self.project1, session=self.session
        )

        # user4 has no preferences, so they should NOT be included (no conflict)
        self.assertNotIn(self.user4, users)

    def test_with_invalid_project_preference_all_have_valid_preference(self):
        """Test when all users with preferences have selected the project (no conflicts)."""
        # Give user2 preference for project1 too
        ProjectPreference.objects.create(
            user=self.user2, session=self.session, project=self.project1
        )

        users = CustomUser.objects.with_invalid_project_preference(
            project=self.project1, session=self.session
        )

        # Now all users with preferences have selected project1
        # So result should be empty (no conflicts)
        self.assertEqual(users.count(), 0)

    def test_queryset_chaining(self):
        """Test that queryset methods can be chained with other filters."""
        users = (
            CustomUser.objects.filter(username__startswith="user")
            .with_project_preference(project=self.project1, session=self.session)
            .order_by("username")
        )

        self.assertEqual(users.count(), 2)
        self.assertEqual(list(users), [self.user1, self.user3])

    def test_distinct_results(self):
        """Test that results are properly de-duplicated."""
        # This tests the .distinct() in the queryset methods
        users = CustomUser.objects.with_project_preference(
            project=self.project1, session=self.session
        )

        # Should not have duplicates even though there might be multiple joins
        user_ids = [u.id for u in users]
        self.assertEqual(len(user_ids), len(set(user_ids)))


class ForComparingAvailabilityTestCase(TestCase):
    """Test CustomUser.objects.for_comparing_availability() queryset method."""

    @classmethod
    def setUpTestData(cls):
        """Create test data once for all tests in this class."""
        cls.session = SessionFactory()
        cls.project = ProjectFactory(name="Django")
        cls.team = Team.objects.create(
            session=cls.session, project=cls.project, name="Team Alpha"
        )
        cls.other_team = Team.objects.create(
            session=cls.session, project=cls.project, name="Team Beta"
        )

        # Create users with availability
        cls.captain = UserFactory(first_name="Captain", last_name="Marvel")
        cls.navigator = UserFactory(first_name="Navigator", last_name="Smith")
        cls.djangonaut = UserFactory(first_name="Django", last_name="Learner")
        cls.other_team_user = UserFactory(first_name="Other", last_name="User")

        UserAvailabilityFactory.create(user=cls.captain, slots=[0.0, 0.5])
        UserAvailabilityFactory.create(user=cls.navigator, slots=[0.0, 1.0])
        UserAvailabilityFactory.create(user=cls.djangonaut, slots=[0.0])
        UserAvailabilityFactory.create(user=cls.other_team_user, slots=[0.0])

        # Create memberships for main team
        cls.captain_membership = SessionMembershipFactory.create(
            session=cls.session,
            team=cls.team,
            user=cls.captain,
            role=SessionMembership.CAPTAIN,
            accepted=True,
        )
        cls.navigator_membership = SessionMembershipFactory.create(
            session=cls.session,
            team=cls.team,
            user=cls.navigator,
            role=SessionMembership.NAVIGATOR,
            accepted=True,
        )
        cls.djangonaut_membership = SessionMembershipFactory.create(
            session=cls.session,
            team=cls.team,
            user=cls.djangonaut,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )

        # Create membership for other team
        SessionMembershipFactory.create(
            session=cls.session,
            team=cls.other_team,
            user=cls.other_team_user,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )

    def test_user_with_permission_sees_all_users_with_availability(self):
        """Users with compare_org_availability permission see all users."""
        user_with_perm = UserFactory()
        content_type = ContentType.objects.get_for_model(Team)
        permission = Permission.objects.get(
            codename="compare_org_availability", content_type=content_type
        )
        user_with_perm.user_permissions.add(permission)

        users = CustomUser.objects.for_comparing_availability(user=user_with_perm)
        user_ids = [u.id for u in users]

        self.assertIn(self.captain.id, user_ids)
        self.assertIn(self.navigator.id, user_ids)
        self.assertIn(self.djangonaut.id, user_ids)
        self.assertIn(self.other_team_user.id, user_ids)

    def test_user_without_permission_or_session_sees_empty_list(self):
        """Users without permission or session context see empty list."""
        user_without_perm = UserFactory()

        users = CustomUser.objects.for_comparing_availability(user=user_without_perm)

        self.assertEqual(list(users), [])

    def test_organizer_sees_all_session_participants(self):
        """Session organizers see all session participants with availability."""
        organizer_membership = OrganizerFactory.create(session=self.session)

        users = CustomUser.objects.for_comparing_availability(
            user=organizer_membership.user,
            session=self.session,
            session_membership=organizer_membership,
        )
        user_ids = [u.id for u in users]

        self.assertIn(self.captain.id, user_ids)
        self.assertIn(self.navigator.id, user_ids)
        self.assertIn(self.djangonaut.id, user_ids)
        self.assertIn(self.other_team_user.id, user_ids)

    def test_team_member_sees_only_team_members(self):
        """Non-organizer team members see only their team members."""
        users = CustomUser.objects.for_comparing_availability(
            user=self.djangonaut,
            session=self.session,
            session_membership=self.djangonaut_membership,
        )
        user_ids = [u.id for u in users]

        self.assertIn(self.captain.id, user_ids)
        self.assertIn(self.navigator.id, user_ids)
        self.assertIn(self.djangonaut.id, user_ids)
        self.assertNotIn(self.other_team_user.id, user_ids)

    def test_non_member_of_session_sees_empty_list(self):
        """User not a member of the session sees empty list."""
        non_member = UserFactory()

        users = CustomUser.objects.for_comparing_availability(
            user=non_member,
            session=self.session,
            session_membership=None,
        )

        self.assertEqual(list(users), [])

    def test_excludes_users_without_availability(self):
        """Users without availability records are excluded."""
        user_no_availability = UserFactory()
        SessionMembershipFactory.create(
            session=self.session,
            team=self.team,
            user=user_no_availability,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )

        users = CustomUser.objects.for_comparing_availability(
            user=self.djangonaut,
            session=self.session,
            session_membership=self.djangonaut_membership,
        )
        user_ids = [u.id for u in users]

        self.assertNotIn(user_no_availability.id, user_ids)

    def test_results_are_ordered_by_name(self):
        """Results are ordered by first_name, last_name."""
        organizer_membership = OrganizerFactory.create(session=self.session)

        users = list(
            CustomUser.objects.for_comparing_availability(
                user=organizer_membership.user,
                session=self.session,
                session_membership=organizer_membership,
            )
        )

        # Verify ordering: Captain Marvel, Django Learner, Navigator Smith, Other User
        names = [(u.first_name, u.last_name) for u in users]
        self.assertEqual(names, sorted(names))

    def test_results_are_distinct(self):
        """Results contain no duplicates."""
        organizer_membership = OrganizerFactory.create(session=self.session)

        users = CustomUser.objects.for_comparing_availability(
            user=organizer_membership.user,
            session=self.session,
            session_membership=organizer_membership,
        )
        user_ids = [u.id for u in users]

        self.assertEqual(len(user_ids), len(set(user_ids)))
