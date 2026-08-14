"""Tests for the Buttondown signal handler in accounts/receivers.py."""

import json

import responses as rsps
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.factories import UserFactory
from accounts.models import ButtondownAccount
from home.factories import SessionMembershipFactory

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

        user.profile.email_confirmed = True
        user.profile.bio = "updated"
        user.profile.save()

        self.assertEqual(len(rsps.calls), 1)
        self.assertEqual(rsps.calls[0].request.method, "PATCH")

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_profile_save_always_triggers_sync_when_configured(self):
        user = UserFactory.create()
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers/{user.email}", status=404)
        rsps.add(
            rsps.POST,
            f"{_BASE_URL}/subscribers",
            json={"id": "new-uuid"},
            status=201,
        )

        user.profile.email_confirmed = True
        user.profile.bio = "updated"
        user.profile.save()

        self.assertGreaterEqual(len(rsps.calls), 1)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_profile_save_triggers_sync_when_opting_in_with_no_account(self):
        user = UserFactory.create()
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers/{user.email}", status=404)
        rsps.add(
            rsps.POST,
            f"{_BASE_URL}/subscribers",
            json={"id": "new-uuid"},
            status=201,
        )

        user.profile.email_confirmed = True
        user.profile.receiving_newsletter = True
        user.profile.save()

        self.assertGreaterEqual(len(rsps.calls), 1)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_profile_save_forwards_ip_address_on_new_subscriber(self):
        user = UserFactory.create()
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers/{user.email}", status=404)
        rsps.add(
            rsps.POST,
            f"{_BASE_URL}/subscribers",
            json={"id": "new-uuid"},
            status=201,
        )

        user.profile.email_confirmed = True
        user.profile._buttondown_ip_address = "203.0.113.5"
        user.profile.save()

        create_call = next(call for call in rsps.calls if call.request.method == "POST")
        body = json.loads(create_call.request.body)
        self.assertEqual(body["ip_address"], "203.0.113.5")

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_new_signup_does_not_trigger_sync_when_email_not_confirmed(self):
        User.objects.create_user(username="newuser", email="new@example.com")

        self.assertEqual(len(rsps.calls), 0)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_profile_save_does_not_sync_when_email_not_confirmed(self):
        user = UserFactory.create()
        ButtondownAccount.objects.create(
            user=user, buttondown_identifier="bd-uuid-signal"
        )

        user.profile.bio = "updated"
        user.profile.save()

        self.assertEqual(len(rsps.calls), 0)

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

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_membership_save_syncs(self):
        """A SessionMembership save syncs Buttondown when the user's email is confirmed."""
        user = UserFactory.create()
        ButtondownAccount.objects.create(
            user=user, buttondown_identifier="bd-uuid-signal"
        )
        rsps.add(
            rsps.PATCH,
            f"{_BASE_URL}/subscribers/bd-uuid-signal",
            json={"id": "bd-uuid-signal"},
        )
        user.profile.email_confirmed = True
        user.profile.save()
        calls_before = len(rsps.calls)

        SessionMembershipFactory.create(user=user)

        self.assertEqual(len(rsps.calls), calls_before + 1)
        self.assertEqual(rsps.calls[-1].request.method, "PATCH")

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_membership_save_unconfirmed_email(self):
        """A SessionMembership save does not sync when the user's email isn't confirmed."""
        user = UserFactory.create()

        SessionMembershipFactory.create(user=user)

        self.assertEqual(len(rsps.calls), 0)

    @override_settings(BUTTONDOWN_API_KEY="")
    @rsps.activate
    def test_membership_save_not_configured(self):
        """A SessionMembership save does not sync when Buttondown isn't configured."""
        user = UserFactory.create()
        user.profile.email_confirmed = True
        user.profile.save()

        SessionMembershipFactory.create(user=user)

        self.assertEqual(len(rsps.calls), 0)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_membership_delete_syncs(self):
        """Deleting a SessionMembership syncs Buttondown when the user's email is confirmed."""
        user = UserFactory.create()
        ButtondownAccount.objects.create(
            user=user, buttondown_identifier="bd-uuid-signal"
        )
        rsps.add(
            rsps.PATCH,
            f"{_BASE_URL}/subscribers/bd-uuid-signal",
            json={"id": "bd-uuid-signal"},
        )
        user.profile.email_confirmed = True
        user.profile.save()
        membership = SessionMembershipFactory.create(user=user)
        calls_before = len(rsps.calls)

        membership.delete()

        self.assertEqual(len(rsps.calls), calls_before + 1)
        self.assertEqual(rsps.calls[-1].request.method, "PATCH")

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_membership_delete_unconfirmed_email(self):
        """Deleting a SessionMembership does not sync when the user's email isn't confirmed."""
        user = UserFactory.create()
        membership = SessionMembershipFactory.create(user=user)

        membership.delete()

        self.assertEqual(len(rsps.calls), 0)
