"""Tests for admin inlines and admin actions."""

from unittest.mock import Mock

from django.contrib import messages
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import TestCase, RequestFactory

from accounts.factories import UserFactory
from accounts.models import UserAvailability
from home.admin import SessionMembershipAdmin, SessionMembershipInline
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


class FindBestAvailabilityOverlapsActionTests(TestCase):
    """Tests for the find_best_availability_overlaps_action admin action."""

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.admin_site = AdminSite()
        self.model_admin = SessionMembershipAdmin(SessionMembership, self.admin_site)
        self.session = SessionFactory.create(title="Test Session")

        self.user1 = UserFactory.create(email="user1@example.com")
        self.user2 = UserFactory.create(email="user2@example.com")
        self.user3 = UserFactory.create(email="user3@example.com")

        self.membership1 = SessionMembershipFactory.create(
            session=self.session,
            user=self.user1,
            role=SessionMembership.DJANGONAUT,
        )
        self.membership2 = SessionMembershipFactory.create(
            session=self.session,
            user=self.user2,
            role=SessionMembership.CAPTAIN,
        )
        self.membership3 = SessionMembershipFactory.create(
            session=self.session,
            user=self.user3,
            role=SessionMembership.NAVIGATOR,
        )

    def test_action_requires_at_least_two_members(self):
        """Test that action shows error when less than 2 members selected."""
        request = self.factory.get("/admin/home/sessionmembership/")
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = SessionMembership.objects.filter(id=self.membership1.id)

        self.model_admin.find_best_availability_overlaps_action(request, queryset)

        message_list = list(request._messages)
        self.assertEqual(len(message_list), 1)
        self.assertEqual(message_list[0].level, messages.ERROR)
        self.assertIn("at least 2 members", str(message_list[0].message))

    def test_action_with_no_availability_data(self):
        """Test action when members have no availability set."""
        request = self.factory.get("/admin/home/sessionmembership/")
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = SessionMembership.objects.filter(
            id__in=[self.membership1.id, self.membership2.id]
        )

        self.model_admin.find_best_availability_overlaps_action(request, queryset)

        message_list = list(request._messages)
        self.assertEqual(len(message_list), 1)
        self.assertEqual(message_list[0].level, messages.WARNING)
        self.assertIn("No overlapping", str(message_list[0].message))

    def test_action_with_overlapping_availability(self):
        """Test action successfully finds overlapping availability."""
        UserAvailability.objects.create(
            user=self.user1,
            slots=[24.0, 24.5, 25.0, 25.5, 26.0, 26.5],
        )
        UserAvailability.objects.create(
            user=self.user2,
            slots=[24.0, 24.5, 25.0, 25.5, 26.0, 26.5],
        )
        UserAvailability.objects.create(
            user=self.user3,
            slots=[24.0, 24.5, 30.0, 30.5],
        )

        request = self.factory.get("/admin/home/sessionmembership/")
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = SessionMembership.objects.filter(
            id__in=[self.membership1.id, self.membership2.id, self.membership3.id]
        )

        self.model_admin.find_best_availability_overlaps_action(request, queryset)

        message_list = list(request._messages)
        self.assertEqual(len(message_list), 1)

        message = str(message_list[0].message)
        self.assertIn("Mon 12:00 AM - 1:00 AM", message)
        self.assertIn("Djangonaut: 1", message)
        self.assertIn("Captain: 1", message)
        self.assertIn("Navigator: 1", message)

    def test_action_shows_unavailable_member_link(self):
        """Test that action includes link to unavailable members."""
        UserAvailability.objects.create(
            user=self.user1,
            slots=[24.0, 24.5],
        )
        UserAvailability.objects.create(
            user=self.user2,
            slots=[24.0, 24.5],
        )
        UserAvailability.objects.create(
            user=self.user3,
            slots=[30.0, 30.5],
        )

        request = self.factory.get("/admin/home/sessionmembership/")
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = SessionMembership.objects.filter(
            id__in=[self.membership1.id, self.membership2.id, self.membership3.id]
        )

        self.model_admin.find_best_availability_overlaps_action(request, queryset)

        message_list = list(request._messages)
        message = str(message_list[0].message)

        self.assertIn("View 1 unavailable member(s)", message)
        self.assertIn("/django-admin/home/sessionmembership/?user_id__in=", message)

    def test_action_shows_all_members_available(self):
        """Test message when all members are available for a time slot."""
        UserAvailability.objects.create(
            user=self.user1,
            slots=[24.0, 24.5],
        )
        UserAvailability.objects.create(
            user=self.user2,
            slots=[24.0, 24.5],
        )

        request = self.factory.get("/admin/home/sessionmembership/")
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = SessionMembership.objects.filter(
            id__in=[self.membership1.id, self.membership2.id]
        )

        self.model_admin.find_best_availability_overlaps_action(request, queryset)

        message_list = list(request._messages)
        message = str(message_list[0].message)

        self.assertIn("All members available!", message)

    def test_action_message_level_based_on_result_count(self):
        """Test that message level is INFO for <5 results, SUCCESS for 5+."""
        UserAvailability.objects.create(
            user=self.user1,
            slots=[24.0, 24.5, 25.0, 25.5],
        )
        UserAvailability.objects.create(
            user=self.user2,
            slots=[24.0, 24.5, 25.0, 25.5],
        )

        request = self.factory.get("/admin/home/sessionmembership/")
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = SessionMembership.objects.filter(
            id__in=[self.membership1.id, self.membership2.id]
        )

        self.model_admin.find_best_availability_overlaps_action(request, queryset)

        message_list = list(request._messages)
        self.assertEqual(message_list[0].level, messages.INFO)
