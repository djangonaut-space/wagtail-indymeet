"""Tests for the sync_buttondown management command."""

import json
from io import StringIO

import responses as rsps
from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.factories import UserFactory
from accounts.models import UserProfile

BD_SETTINGS = {"BUTTONDOWN_API_KEY": "test-api-key"}
_BASE_URL = "https://api.buttondown.email/v1"


class SyncButtondownCommandTests(TestCase):
    """
    Management command tests use ImmediateBackend, so enqueued tasks run
    synchronously. responses intercepts at the HTTP layer to verify the correct
    users are synced without making real API calls.

    Profile email_confirmed flags are set via queryset .update() to bypass
    signals during test setup — only the command run itself triggers HTTP calls.
    """

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_syncs_active_confirmed_users(self):
        active1 = UserFactory.create(is_active=True)
        UserProfile.objects.filter(pk=active1.profile.pk).update(email_confirmed=True)
        active2 = UserFactory.create(is_active=True)
        UserProfile.objects.filter(pk=active2.profile.pk).update(email_confirmed=True)
        UserFactory.create(is_active=False)

        _ids = iter(["uuid-cmd-1", "uuid-cmd-2"])

        def _create_subscriber(request):
            return (201, {}, json.dumps({"id": next(_ids)}))

        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers", json={"results": []})
        rsps.add_callback(
            rsps.POST, f"{_BASE_URL}/subscribers", callback=_create_subscriber
        )

        call_command("sync_buttondown", stdout=StringIO(), stderr=StringIO())

        get_calls = [c for c in rsps.calls if c.request.method == "GET"]
        self.assertEqual(len(get_calls), 2)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_skips_users_with_unconfirmed_email(self):
        user = UserFactory.create(is_active=True)
        UserProfile.objects.filter(pk=user.profile.pk).update(email_confirmed=False)

        call_command("sync_buttondown", stdout=StringIO(), stderr=StringIO())

        self.assertEqual(len(rsps.calls), 0)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_dry_run_does_not_sync(self):
        user = UserFactory.create(is_active=True)
        UserProfile.objects.filter(pk=user.profile.pk).update(email_confirmed=True)

        out = StringIO()
        call_command("sync_buttondown", dry_run=True, stdout=out, stderr=StringIO())

        self.assertEqual(len(rsps.calls), 0)
        self.assertIn("Dry run", out.getvalue())

    @override_settings(BUTTONDOWN_API_KEY="")
    @rsps.activate
    def test_aborts_when_not_configured(self):
        user = UserFactory.create(is_active=True)
        UserProfile.objects.filter(pk=user.profile.pk).update(email_confirmed=True)

        err = StringIO()
        call_command("sync_buttondown", stdout=StringIO(), stderr=err)

        self.assertEqual(len(rsps.calls), 0)
        self.assertIn("BUTTONDOWN_API_KEY", err.getvalue())
