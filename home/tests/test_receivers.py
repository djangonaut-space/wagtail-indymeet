from datetime import timedelta
from io import StringIO

from django.apps import apps
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from wagtail.models import Collection, Page, Site

from accounts.factories import UserFactory
from home import constants
from home.factories import SessionFactory, SessionMembershipFactory
from home.models import HomePage
from home.models.session import SessionMembership
from home.receivers import (
    WAGTAIL_PLACEHOLDER_TITLE,
    ensure_site_structure,
    is_fully_migrated,
)


class OrganizerReceiversHandlersTestCase(TestCase):
    """Tests for receivers that manage organizer group membership."""

    def setUp(self):
        call_command("setup_session_organizers_group", stdout=StringIO())
        self.group = Group.objects.get(name="Session Organizers")
        self.today = timezone.now().date()
        self.start_date = self.today - timedelta(days=10)
        self.end_date = self.today + timedelta(days=30)
        self.invitation_date = self.today - timedelta(days=20)
        self.application_start_date = self.today - timedelta(days=30)
        self.application_end_date = self.today - timedelta(days=25)
        self.session = SessionFactory.create(
            start_date=self.start_date,
            end_date=self.end_date,
            invitation_date=self.invitation_date,
            application_start_date=self.application_start_date,
            application_end_date=self.application_end_date,
        )

    def test_adds_regular_user_to_group_when_organizer_created(self):
        """Test that creating organizer membership adds user to group."""
        user = UserFactory(is_staff=False, is_superuser=False)

        SessionMembershipFactory(
            user=user, session=self.session, role=constants.ORGANIZER
        )

        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertIn(self.group, user.groups.all())

    def test_makes_user_staff_when_organizer_created(self):
        """Test that creating organizer membership makes user staff."""
        user = UserFactory(is_staff=False, is_superuser=False)

        SessionMembershipFactory(
            user=user, session=self.session, role=constants.ORGANIZER
        )

        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_skips_superuser(self):
        """Test that superusers are not added to group."""
        user = UserFactory(is_staff=True, is_superuser=True)
        session = SessionFactory()

        SessionMembershipFactory(user=user, session=session, role=constants.ORGANIZER)

        user.refresh_from_db()
        self.assertNotIn(self.group, user.groups.all())

    def test_signal_is_idempotent(self):
        """Test that saving membership multiple times doesn't cause issues."""
        user = UserFactory(is_staff=False, is_superuser=False)

        membership = SessionMembershipFactory(
            user=user, session=self.session, role=constants.ORGANIZER
        )

        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertIn(self.group, user.groups.all())

        membership.save()

        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertEqual(user.groups.filter(name="Session Organizers").count(), 1)

    def test_does_not_add_non_organizer_to_group(self):
        """Test that non-organizer roles don't add user to group."""
        user = UserFactory(is_staff=False, is_superuser=False)
        session = SessionFactory()

        SessionMembershipFactory(user=user, session=session, role=constants.DJANGONAUT)

        user.refresh_from_db()
        self.assertNotIn(self.group, user.groups.all())
        self.assertFalse(user.is_staff)


class EnsureSiteStructureTests(TestCase):
    def test_recreates_missing_rows(self):
        """Simulates what a flush leaves behind: no site or home page."""
        Site.objects.all().delete()
        HomePage.objects.all().delete()

        ensure_site_structure(sender=apps.get_app_config("home"))

        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(HomePage.objects.count(), 1)

    def test_replaces_wagtail_placeholder(self):
        """A new database has Wagtail's welcome page as the site root, not a HomePage."""
        HomePage.objects.all().delete()
        placeholder = Page.get_first_root_node().add_child(
            instance=Page(title=WAGTAIL_PLACEHOLDER_TITLE, slug="home")
        )
        Site.objects.create(
            hostname="localhost", root_page=placeholder, is_default_site=True
        )

        ensure_site_structure(sender=apps.get_app_config("home"))

        self.assertFalse(Page.objects.filter(pk=placeholder.pk).exists())
        self.assertIsInstance(Site.objects.get().root_page.specific, HomePage)

    def test_keeps_other_home_page(self):
        """A "home" page that isn't Wagtail's untouched placeholder is never deleted."""
        HomePage.objects.all().delete()
        page = Page.get_first_root_node().add_child(
            instance=Page(title="Our home", slug="home")
        )

        with self.assertRaises(ValidationError):
            ensure_site_structure(sender=apps.get_app_config("home"))

        self.assertTrue(Page.objects.filter(pk=page.pk).exists())

    def test_keeps_existing_rows(self):
        site = Site.objects.get()
        counts = (Page.objects.count(), Collection.objects.count())

        ensure_site_structure(sender=apps.get_app_config("home"), plan=[])

        self.assertEqual(Site.objects.get(), site)
        self.assertEqual((Page.objects.count(), Collection.objects.count()), counts)

    def test_fully_migrated(self):
        self.assertTrue(is_fully_migrated("default"))
