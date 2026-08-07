"""Tests for AnnouncementAdmin's post action and organizer scoping."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts.factories import UserFactory
from home import constants
from home.admin import AnnouncementAdmin
from home.factories import (
    AnnouncementFactory,
    SessionFactory,
    SessionMembershipFactory,
)
from home.models import Announcement


class AnnouncementAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(
            email="admin@example.com", is_staff=True, is_superuser=True
        )
        cls.session = SessionFactory.create(
            discord_category_id="cat-1",
            discord_announcements_channel_id="chan-1",
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = AnnouncementAdmin(Announcement, AdminSite())

    def _get_request(self, user=None):
        request = self.factory.post("/admin/home/announcement/")
        request.user = user or self.superuser

        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))

        return request

    @patch("home.tasks.post_announcement")
    def test_post_action(self, mock_task):
        approved = AnnouncementFactory(session=self.session, needs_approval=False)

        self.admin.post_announcements_action(
            self._get_request(), Announcement.objects.filter(pk=approved.pk)
        )

        mock_task.enqueue.assert_called_once_with(announcement_id=approved.pk)

    @patch("home.tasks.post_announcement")
    def test_post_action_skips(self, mock_task):
        """Unapproved, already-posted and Discord-less rows are left alone."""
        AnnouncementFactory(session=self.session, needs_approval=True, approved_at=None)
        AnnouncementFactory(
            session=self.session, needs_approval=False, posted_at=timezone.now()
        )
        AnnouncementFactory(
            session=SessionFactory(
                discord_category_id="", discord_announcements_channel_id=""
            ),
            needs_approval=False,
        )

        self.admin.post_announcements_action(
            self._get_request(), Announcement.objects.all()
        )

        mock_task.enqueue.assert_not_called()

    def test_queryset_scoping(self):
        """Organizers see only their sessions' announcements; superusers see all."""
        organizer = UserFactory.create(is_staff=True)
        SessionMembershipFactory(
            session=self.session, user=organizer, role=constants.ORGANIZER
        )
        theirs = AnnouncementFactory(session=self.session)
        other = AnnouncementFactory()

        self.assertCountEqual(
            self.admin.get_queryset(self._get_request(organizer)), [theirs]
        )
        self.assertCountEqual(
            self.admin.get_queryset(self._get_request()), [theirs, other]
        )

    def test_approved_display(self):
        """The column reflects real approval state, not the raw boolean."""
        not_required = AnnouncementFactory(session=self.session, needs_approval=False)
        pending = AnnouncementFactory(
            session=self.session, needs_approval=True, approved_at=None
        )
        approved = AnnouncementFactory(
            session=self.session, needs_approval=True, approved_at=timezone.now()
        )

        self.assertIs(self.admin.approved(not_required), True)
        self.assertIs(self.admin.approved(pending), False)
        self.assertIs(self.admin.approved(approved), True)
