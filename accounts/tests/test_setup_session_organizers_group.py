from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase


class SetupSessionOrganizersGroupCommandTestCase(TestCase):
    """Tests for the setup_session_organizers_group management command."""

    def test_creates_group_with_permissions(self):
        """Test that management command creates group with correct permissions."""
        call_command("setup_session_organizers_group")

        group = Group.objects.get(name="Session Organizers")
        permissions = group.permissions.all()
        self.assertGreaterEqual(len(permissions), 27)

        permission_codenames = [p.codename for p in permissions]
        self.assertIn("view_customuser", permission_codenames)
        self.assertIn("view_session", permission_codenames)
        self.assertIn("add_session", permission_codenames)
        self.assertIn("view_userprofile", permission_codenames)
        self.assertIn("add_userprofile", permission_codenames)
        self.assertIn("change_userprofile", permission_codenames)
        self.assertIn("view_sessionmembership", permission_codenames)
        self.assertIn("add_sessionmembership", permission_codenames)
        self.assertIn("change_sessionmembership", permission_codenames)
        self.assertIn("form_team", permission_codenames)

    def test_command_is_idempotent(self):
        """Test that running command multiple times works correctly."""
        call_command("setup_session_organizers_group")
        first_group = Group.objects.get(name="Session Organizers")
        first_perm_count = first_group.permissions.count()

        call_command("setup_session_organizers_group")
        second_group = Group.objects.get(name="Session Organizers")
        second_perm_count = second_group.permissions.count()

        self.assertEqual(first_group.pk, second_group.pk)
        self.assertEqual(first_perm_count, second_perm_count)
