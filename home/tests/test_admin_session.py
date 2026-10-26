"""Tests for SessionAdmin configuration."""

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from accounts.factories import UserFactory
from home.admin import SessionAdmin
from home.factories import SessionFactory
from home.models import Session


class SessionAdminReadonlyFieldsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.session = SessionFactory.create()

    def test_workflow_fields_not_in_form(self):
        """Fields set by the email and Discord workflows are shown but not
        editable."""
        request = RequestFactory().get("/admin/home/session/")
        request.user = self.superuser
        model_admin = SessionAdmin(Session, AdminSite())

        form = model_admin.get_form(request, self.session)

        for field in (
            "results_notifications_sent_at",
            "djangonauts_have_access",
            "discord_category_id",
            "discord_announcements_channel_id",
            "discord_capnav_channel_id",
        ):
            self.assertNotIn(field, form.base_fields)
            self.assertIn(field, model_admin.get_fields(request, self.session))
