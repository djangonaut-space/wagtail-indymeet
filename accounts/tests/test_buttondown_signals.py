"""Tests for the Buttondown signal handler in accounts/receivers.py."""

import responses as rsps
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.factories import UserFactory
from accounts.models import ButtondownAccount

BD_SETTINGS = {"BUTTONDOWN_API_KEY": "test-api-key"}
_BASE_URL = "https://api.buttondown.email/v1"

User = get_user_model()


class ButtondownSignalTests(TestCase):
    """
    Signal tests verify the full signal→task→service→HTTP chain.
    responses intercepts at the HTTP layer; tasks run synchronously via
    ImmediateBackend configured in test settings.
    """

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_profile_save_triggers_sync_when_account_exists(self):
        user = UserFactory.create()
        ButtondownAccount.objects.create(
            user=user, buttondown_identifier="bd-uuid-signal"
        )
        rsps.add(
            rsps.PATCH,
            f"{_BASE_URL}/subscribers/bd-uuid-signal",
            json={"id": "bd-uuid-signal"},
        )

        user.profile.bio = "updated"
        user.profile.save()

        self.assertEqual(len(rsps.calls), 1)
        self.assertEqual(rsps.calls[0].request.method, "PATCH")

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_profile_save_always_triggers_sync_when_configured(self):
        user = UserFactory.create()
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers", json={"results": []})
        rsps.add(
            rsps.POST,
            f"{_BASE_URL}/subscribers",
            json={"id": "new-uuid"},
            status=201,
        )

        user.profile.bio = "updated"
        user.profile.save()

        self.assertGreaterEqual(len(rsps.calls), 1)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_profile_save_triggers_sync_when_opting_in_with_no_account(self):
        user = UserFactory.create()
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers", json={"results": []})
        rsps.add(
            rsps.POST,
            f"{_BASE_URL}/subscribers",
            json={"id": "new-uuid"},
            status=201,
        )

        user.profile.receiving_newsletter = True
        user.profile.save()

        self.assertGreaterEqual(len(rsps.calls), 1)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_new_signup_triggers_sync(self):
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers", json={"results": []})
        rsps.add(
            rsps.POST,
            f"{_BASE_URL}/subscribers",
            json={"id": "new-uuid"},
            status=201,
        )

        User.objects.create_user(username="newuser", email="new@example.com")

        self.assertGreaterEqual(len(rsps.calls), 1)

    @override_settings(BUTTONDOWN_API_KEY="")
    @rsps.activate
    def test_profile_save_does_not_sync_when_not_configured(self):
        user = UserFactory.create()
        ButtondownAccount.objects.create(
            user=user, buttondown_identifier="bd-uuid-signal"
        )

        user.profile.bio = "updated"
        user.profile.save()

        self.assertEqual(len(rsps.calls), 0)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_raw_save_does_not_trigger_sync(self):
        user = UserFactory.create()

        user.profile.bio = "updated"
        user.profile.save_base(raw=True)

        self.assertEqual(len(rsps.calls), 0)
