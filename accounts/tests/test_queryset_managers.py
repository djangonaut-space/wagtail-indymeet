"""Tests for CustomUser queryset managers and methods."""

from django.test import TestCase

from accounts.factories import UserFactory
from accounts.models import CustomUser
from home.factories import ProjectFactory, SessionFactory
from home.models import ProjectPreference


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
