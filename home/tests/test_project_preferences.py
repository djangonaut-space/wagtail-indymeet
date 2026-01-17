"""Tests for project preferences functionality."""

from django.test import TestCase

from accounts.factories import UserFactory
from home.factories import ProjectFactory, SessionFactory
from home.models import ProjectPreference


class ProjectPreferenceQuerySetTestCase(TestCase):
    """Test ProjectPreference queryset methods."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.session1 = SessionFactory(title="Session 1")
        cls.session2 = SessionFactory(title="Session 2")

        cls.project1 = ProjectFactory(name="Django")
        cls.project2 = ProjectFactory(name="Wagtail")

        cls.user1 = UserFactory(username="user1")
        cls.user2 = UserFactory(username="user2")

        # User1 preferences for session1
        cls.pref1 = ProjectPreference.objects.create(
            user=cls.user1, session=cls.session1, project=cls.project1
        )
        cls.pref2 = ProjectPreference.objects.create(
            user=cls.user1, session=cls.session1, project=cls.project2
        )

        # User2 preferences for session1
        cls.pref3 = ProjectPreference.objects.create(
            user=cls.user2, session=cls.session1, project=cls.project1
        )

        # User1 preferences for session2
        cls.pref4 = ProjectPreference.objects.create(
            user=cls.user1, session=cls.session2, project=cls.project1
        )

    def test_for_user_session(self):
        """Test filtering preferences for a specific user and session."""
        prefs = ProjectPreference.objects.for_user_session(
            user=self.user1, session=self.session1
        )

        self.assertEqual(prefs.count(), 2)
        self.assertIn(self.pref1, prefs)
        self.assertIn(self.pref2, prefs)
        self.assertNotIn(self.pref3, prefs)
        self.assertNotIn(self.pref4, prefs)

    def test_for_user_session_no_preferences(self):
        """Test filtering when user has no preferences for session."""
        prefs = ProjectPreference.objects.for_user_session(
            user=self.user2, session=self.session2
        )

        self.assertEqual(prefs.count(), 0)

    def test_for_session(self):
        """Test filtering preferences for a specific session."""
        prefs = ProjectPreference.objects.for_session(session=self.session1)

        self.assertEqual(prefs.count(), 3)
        self.assertIn(self.pref1, prefs)
        self.assertIn(self.pref2, prefs)
        self.assertIn(self.pref3, prefs)
        self.assertNotIn(self.pref4, prefs)

    def test_for_user_session_exclude_project(self):
        """Test excluding specific projects from user session preferences."""
        # Get user1's session1 preferences excluding project1
        prefs = ProjectPreference.objects.for_user_session(
            user=self.user1, session=self.session1
        ).exclude(project=self.project1)

        self.assertEqual(prefs.count(), 1)
        self.assertEqual(prefs.first(), self.pref2)


class ProjectPreferenceModelTestCase(TestCase):
    """Test ProjectPreference model methods and constraints."""

    def setUp(self):
        """Create test data."""
        self.session = SessionFactory()
        self.project = ProjectFactory()
        self.user = UserFactory()

    def test_str_representation(self):
        """Test string representation of ProjectPreference."""
        pref = ProjectPreference.objects.create(
            user=self.user, session=self.session, project=self.project
        )

        expected = f"{self.user.username} - {self.project.name} ({self.session.title})"
        self.assertEqual(str(pref), expected)

    def test_unique_constraint(self):
        """Test that the same user/session/project combination can't be created twice."""
        ProjectPreference.objects.create(
            user=self.user, session=self.session, project=self.project
        )

        # Attempting to create duplicate should be prevented by unique constraint
        # Using bulk_create with ignore_conflicts=True like the forms do
        duplicate = ProjectPreference(
            user=self.user, session=self.session, project=self.project
        )

        # This should not raise an error due to ignore_conflicts
        ProjectPreference.objects.bulk_create([duplicate], ignore_conflicts=True)

        # Should still only have one preference
        count = ProjectPreference.objects.for_user_session(
            user=self.user, session=self.session
        ).count()
        self.assertEqual(count, 1)

    def test_multiple_projects_same_session(self):
        """Test that a user can have preferences for multiple projects in same session."""
        project2 = ProjectFactory()

        ProjectPreference.objects.create(
            user=self.user, session=self.session, project=self.project
        )
        ProjectPreference.objects.create(
            user=self.user, session=self.session, project=project2
        )

        prefs = ProjectPreference.objects.for_user_session(
            user=self.user, session=self.session
        )
        self.assertEqual(prefs.count(), 2)

    def test_same_project_different_sessions(self):
        """Test that a user can have the same project preference for different sessions."""
        session2 = SessionFactory()

        ProjectPreference.objects.create(
            user=self.user, session=self.session, project=self.project
        )
        ProjectPreference.objects.create(
            user=self.user, session=session2, project=self.project
        )

        # Should have one preference in each session
        session1_prefs = ProjectPreference.objects.for_user_session(
            user=self.user, session=self.session
        )
        session2_prefs = ProjectPreference.objects.for_user_session(
            user=self.user, session=session2
        )

        self.assertEqual(session1_prefs.count(), 1)
        self.assertEqual(session2_prefs.count(), 1)
