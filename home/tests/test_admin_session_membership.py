"""Tests for admin inlines."""

from unittest.mock import Mock

from django.contrib.admin.sites import AdminSite
from django.test import TestCase, RequestFactory

from accounts.factories import UserFactory
from home.admin import SessionMembershipInline
from home.factories import SessionFactory, SessionMembershipFactory, TeamFactory
from home.models import Session, SessionMembership


class SessionMembershipInlineTests(TestCase):
    """Tests for SessionMembershipInline queryset filtering."""

    def setUp(self):
        """Set up test data."""
        # Create two sessions with their own teams
        self.session1 = SessionFactory.create(title="Session 1", slug="session-1")
        self.session2 = SessionFactory.create(title="Session 2", slug="session-2")

        self.team1_session1 = TeamFactory.create(
            session=self.session1, name="Team 1 Session 1"
        )
        self.team2_session1 = TeamFactory.create(
            session=self.session1, name="Team 2 Session 1"
        )
        self.team1_session2 = TeamFactory.create(
            session=self.session2, name="Team 1 Session 2"
        )

        self.user = UserFactory.create(email="user@example.com")
        self.factory = RequestFactory()
        self.admin_site = AdminSite()
        self.inline = SessionMembershipInline(
            parent_model=Session, admin_site=self.admin_site
        )

    def test_formfield_limits_teams_to_session(self):
        """Test that team choices are limited to the session being edited."""
        # Create a mock request with session1 as the object_id
        request = self.factory.get("/admin/home/session/123/change/")
        request.resolver_match = Mock()
        request.resolver_match.kwargs = {"object_id": str(self.session1.id)}

        # Get the team field from the model
        team_field = self.inline.model._meta.get_field("team")

        # Call formfield_for_foreignkey
        formfield = self.inline.formfield_for_foreignkey(team_field, request)

        # Team queryset should only include teams from session1
        team_ids = list(formfield.queryset.values_list("id", flat=True))

        self.assertIn(self.team1_session1.id, team_ids)
        self.assertIn(self.team2_session1.id, team_ids)
        self.assertNotIn(self.team1_session2.id, team_ids)
        self.assertEqual(len(team_ids), 2)

    def test_formfield_shows_no_teams_when_no_session(self):
        """Test that no teams are shown when session cannot be determined."""
        # Create a mock request without object_id (adding new session)
        request = self.factory.get("/admin/home/session/add/")
        request.resolver_match = Mock()
        request.resolver_match.kwargs = {}

        # Get the team field from the model
        team_field = self.inline.model._meta.get_field("team")

        # Call formfield_for_foreignkey
        formfield = self.inline.formfield_for_foreignkey(team_field, request)

        # Team queryset should be empty
        self.assertEqual(formfield.queryset.count(), 0)
