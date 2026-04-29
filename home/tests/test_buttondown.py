"""
Tests for Buttondown newsletter sync: ButtondownClient, service layer,
background tasks, signal handlers, and the management command.
"""

import json
from io import StringIO
from unittest.mock import patch

import requests
import responses as rsps
from django.test import TestCase, override_settings

from accounts.factories import UserFactory
from accounts.models import ButtondownAccount
from home import constants
from home.factories import SessionFactory, SessionMembershipFactory
from home.integrations.buttondown.client import ButtondownClient
from home.integrations.buttondown.service import (
    SESSION_SLUG_TO_TAG,
    buttondown_enabled,
    buttondown_service,
    get_tags_for_user,
)
from home.tasks.sync_buttondown import (
    remove_user_from_buttondown,
    sync_user_to_buttondown,
)

BD_SETTINGS = {"BUTTONDOWN_API_KEY": "test-api-key"}


# ---------------------------------------------------------------------------
# buttondown_enabled()
# ---------------------------------------------------------------------------


class ButtondownEnabledTests(TestCase):
    @override_settings(BUTTONDOWN_API_KEY="key")
    def test_returns_true_when_api_key_present(self):
        self.assertTrue(buttondown_enabled())

    @override_settings(BUTTONDOWN_API_KEY="")
    def test_returns_false_when_api_key_empty(self):
        self.assertFalse(buttondown_enabled())

    @override_settings(BUTTONDOWN_API_KEY=None)
    def test_returns_false_when_api_key_none(self):
        self.assertFalse(buttondown_enabled())


# ---------------------------------------------------------------------------
# ButtondownClient
# ---------------------------------------------------------------------------


_BASE_URL = "https://api.buttondown.email/v1"


class ButtondownClientTests(TestCase):
    def setUp(self):
        self.bd_client = ButtondownClient()

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_get_subscriber_by_email_found(self):
        subscriber = {"id": "uuid-123", "email": "foo@example.com"}
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers", json={"results": [subscriber]})

        result = self.bd_client.get_subscriber_by_email("foo@example.com")

        self.assertEqual(result, subscriber)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_get_subscriber_by_email_not_found(self):
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers", json={"results": []})

        result = self.bd_client.get_subscriber_by_email("nobody@example.com")

        self.assertIsNone(result)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_get_subscriber_by_email_sends_correct_params(self):
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers", json={"results": []})

        self.bd_client.get_subscriber_by_email("foo@example.com")

        req = rsps.calls[0].request
        self.assertIn("email=foo%40example.com", req.url)
        self.assertEqual(req.headers["Authorization"], "Token test-api-key")

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_create_subscriber(self):
        rsps.add(
            rsps.POST,
            f"{_BASE_URL}/subscribers",
            json={"id": "new-uuid", "email": "new@example.com"},
            status=201,
        )

        result = self.bd_client.create_subscriber("new@example.com", ["website"])

        self.assertEqual(result["id"], "new-uuid")
        body = json.loads(rsps.calls[0].request.body)
        self.assertEqual(body, {"email": "new@example.com", "tags": ["website"]})

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_patch_subscriber(self):
        payload = {"tags": ["Admin"], "subscriber_type": "regular"}
        rsps.add(
            rsps.PATCH,
            f"{_BASE_URL}/subscribers/uuid-123",
            json={"id": "uuid-123", "tags": ["Admin"]},
        )

        result = self.bd_client.patch_subscriber("uuid-123", payload)

        self.assertEqual(result["id"], "uuid-123")
        body = json.loads(rsps.calls[0].request.body)
        self.assertEqual(body, payload)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_delete_subscriber_returns_none(self):
        rsps.add(rsps.DELETE, f"{_BASE_URL}/subscribers/uuid-123", status=204)

        result = self.bd_client.delete_subscriber("uuid-123")

        self.assertIsNone(result)

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_request_raises_on_http_error(self):
        # 404 is not in status_forcelist so retries don't fire; raise_for_status raises HTTPError
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers", status=404)

        with self.assertRaises(requests.HTTPError):
            self.bd_client.get_subscriber_by_email("foo@example.com")

    @override_settings(**BD_SETTINGS)
    @rsps.activate
    def test_authorization_header_uses_token_scheme(self):
        rsps.add(rsps.GET, f"{_BASE_URL}/subscribers", json={"results": []})

        self.bd_client.get_subscriber_by_email("x@example.com")

        auth = rsps.calls[0].request.headers["Authorization"]
        self.assertTrue(auth.startswith("Token "))


# ---------------------------------------------------------------------------
# get_tags_for_user()
# ---------------------------------------------------------------------------


class GetTagsForUserTests(TestCase):
    def _make_user(self, interested_in=None, is_superuser=False):
        user = UserFactory.create(is_superuser=is_superuser)
        if interested_in is not None:
            user.profile.interested_in = interested_in
            user.profile.save()
        return user

    def test_interested_in_djangonaut_tag(self):
        user = self._make_user(interested_in=[constants.DJANGONAUT])
        self.assertIn("Interested Djangonaut", get_tags_for_user(user))

    def test_interested_in_multiple_roles(self):
        user = self._make_user(interested_in=[constants.CAPTAIN, constants.NAVIGATOR])
        tags = get_tags_for_user(user)
        self.assertIn("Interested Captain", tags)
        self.assertIn("Interested Navigator", tags)

    def test_unknown_interested_in_role_skipped(self):
        user = self._make_user(interested_in=["Alien"])
        tags = get_tags_for_user(user)
        self.assertNotIn("Alien", tags)
        self.assertNotIn("Interested Alien", tags)

    def test_session_tag_from_known_slug(self):
        user = self._make_user()
        session = SessionFactory.create(slug="2024-session-1")
        SessionMembershipFactory.create(
            user=user, session=session, role=constants.DJANGONAUT, accepted=True
        )
        self.assertIn("Session 1", get_tags_for_user(user))

    def test_session_tag_all_known_slugs(self):
        user = self._make_user()
        for slug, expected_tag in SESSION_SLUG_TO_TAG.items():
            session = SessionFactory.create(slug=slug)
            SessionMembershipFactory.create(
                user=user, session=session, role=constants.ORGANIZER
            )
            self.assertIn(expected_tag, get_tags_for_user(user))

    def test_unknown_session_slug_skipped(self):
        user = self._make_user()
        session = SessionFactory.create(slug="unknown-session")
        SessionMembershipFactory.create(
            user=user, session=session, role=constants.DJANGONAUT, accepted=True
        )
        tags = get_tags_for_user(user)
        self.assertNotIn("Session 0", tags)
        self.assertNotIn("Session 1", tags)

    def test_role_tag_djangonaut(self):
        user = self._make_user()
        SessionMembershipFactory.create(
            user=user, role=constants.DJANGONAUT, accepted=True
        )
        self.assertIn("Djangonaut", get_tags_for_user(user))

    def test_role_tag_navigator(self):
        user = self._make_user()
        SessionMembershipFactory.create(user=user, role=constants.NAVIGATOR)
        self.assertIn("Navigator", get_tags_for_user(user))

    def test_role_tag_captain(self):
        user = self._make_user()
        SessionMembershipFactory.create(user=user, role=constants.CAPTAIN)
        self.assertIn("Captain", get_tags_for_user(user))

    def test_role_tag_organizer(self):
        user = self._make_user()
        SessionMembershipFactory.create(user=user, role=constants.ORGANIZER)
        self.assertIn("Organizer", get_tags_for_user(user))

    def test_role_tags_deduplicated_across_sessions(self):
        user = self._make_user()
        SessionMembershipFactory.create(
            user=user, role=constants.DJANGONAUT, accepted=True
        )
        SessionMembershipFactory.create(
            user=user, role=constants.DJANGONAUT, accepted=True
        )
        tags = get_tags_for_user(user)
        self.assertEqual(tags.count("Djangonaut"), 1)

    def test_in_community_tag_when_role_tag_present(self):
        user = self._make_user()
        SessionMembershipFactory.create(
            user=user, role=constants.DJANGONAUT, accepted=True
        )
        self.assertIn("In Community", get_tags_for_user(user))

    def test_in_community_absent_with_no_role_tags(self):
        user = self._make_user(interested_in=[constants.DJANGONAUT])
        self.assertNotIn("In Community", get_tags_for_user(user))

    def test_admin_tag_for_superuser(self):
        user = self._make_user(is_superuser=True)
        self.assertIn("Admin", get_tags_for_user(user))

    def test_admin_tag_absent_for_regular_user(self):
        user = self._make_user()
        self.assertNotIn("Admin", get_tags_for_user(user))

    def test_website_tag_never_returned(self):
        user = self._make_user()
        SessionMembershipFactory.create(
            user=user, role=constants.DJANGONAUT, accepted=True
        )
        self.assertNotIn("website", get_tags_for_user(user))

    def test_unaccepted_djangonaut_membership_excluded(self):
        user = self._make_user()
        SessionMembershipFactory.create(
            user=user, role=constants.DJANGONAUT, accepted=False
        )
        tags = get_tags_for_user(user)
        self.assertNotIn("Djangonaut", tags)
        self.assertNotIn("In Community", tags)

    def test_empty_interested_in_produces_no_interested_tags(self):
        user = self._make_user(interested_in=[])
        tags = get_tags_for_user(user)
        self.assertFalse(any(t.startswith("Interested") for t in tags))


# ---------------------------------------------------------------------------
# ButtondownService._first_sync
# ---------------------------------------------------------------------------


class ButtondownServiceFirstSyncTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.user.profile.receiving_newsletter = False
        self.user.profile.save()

    @override_settings(**BD_SETTINGS)
    def test_first_sync_links_existing_subscriber(self):
        existing = {"id": "bd-uuid-existing"}
        with (
            patch.object(
                buttondown_service.client,
                "get_subscriber_by_email",
                return_value=existing,
            ),
            patch.object(buttondown_service.client, "patch_subscriber") as mock_patch,
        ):
            buttondown_service.sync_user(self.user)

        self.assertTrue(ButtondownAccount.objects.filter(user=self.user).exists())
        account = ButtondownAccount.objects.get(user=self.user)
        self.assertEqual(account.buttondown_identifier, "bd-uuid-existing")

    @override_settings(**BD_SETTINGS)
    def test_first_sync_sets_receiving_newsletter_true_when_existing(self):
        existing = {"id": "bd-uuid-existing"}
        with (
            patch.object(
                buttondown_service.client,
                "get_subscriber_by_email",
                return_value=existing,
            ),
            patch.object(buttondown_service.client, "patch_subscriber"),
        ):
            buttondown_service.sync_user(self.user)

        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.receiving_newsletter)

    @override_settings(**BD_SETTINGS)
    def test_first_sync_patches_tags_for_existing_without_website_tag(self):
        existing = {"id": "bd-uuid-existing"}
        with (
            patch.object(
                buttondown_service.client,
                "get_subscriber_by_email",
                return_value=existing,
            ),
            patch.object(buttondown_service.client, "patch_subscriber") as mock_patch,
        ):
            buttondown_service.sync_user(self.user)

        tags_arg = mock_patch.call_args.args[1]["tags"]
        self.assertNotIn("website", tags_arg)

    @override_settings(**BD_SETTINGS)
    def test_first_sync_creates_new_subscriber_when_not_found(self):
        with (
            patch.object(
                buttondown_service.client,
                "get_subscriber_by_email",
                return_value=None,
            ),
            patch.object(
                buttondown_service.client,
                "create_subscriber",
                return_value={"id": "bd-uuid-new"},
            ) as mock_create,
        ):
            buttondown_service.sync_user(self.user)

        mock_create.assert_called_once()
        self.assertTrue(ButtondownAccount.objects.filter(user=self.user).exists())

    @override_settings(**BD_SETTINGS)
    def test_first_sync_new_subscriber_includes_website_tag(self):
        with (
            patch.object(
                buttondown_service.client,
                "get_subscriber_by_email",
                return_value=None,
            ),
            patch.object(
                buttondown_service.client,
                "create_subscriber",
                return_value={"id": "bd-uuid-new"},
            ) as mock_create,
        ):
            buttondown_service.sync_user(self.user)

        tags_arg = mock_create.call_args.args[1]
        self.assertIn("website", tags_arg)

    @override_settings(**BD_SETTINGS)
    def test_first_sync_new_subscriber_does_not_set_receiving_newsletter(self):
        with (
            patch.object(
                buttondown_service.client,
                "get_subscriber_by_email",
                return_value=None,
            ),
            patch.object(
                buttondown_service.client,
                "create_subscriber",
                return_value={"id": "bd-uuid-new"},
            ),
        ):
            buttondown_service.sync_user(self.user)

        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.receiving_newsletter)


# ---------------------------------------------------------------------------
# ButtondownService._subsequent_sync
# ---------------------------------------------------------------------------


class ButtondownServiceSubsequentSyncTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.user.profile.receiving_newsletter = True
        self.user.profile.save()
        self.bd_account = ButtondownAccount.objects.create(
            user=self.user, buttondown_identifier="bd-uuid-sub"
        )

    @override_settings(**BD_SETTINGS)
    def test_subsequent_sync_updates_tags_when_newsletter_true(self):
        with patch.object(buttondown_service.client, "patch_subscriber") as mock_patch:
            buttondown_service.sync_user(self.user)

        payload = mock_patch.call_args.args[1]
        self.assertEqual(payload["subscriber_type"], "regular")
        self.assertIn("tags", payload)

    @override_settings(**BD_SETTINGS)
    def test_subsequent_sync_unsubscribes_when_newsletter_false(self):
        self.user.profile.receiving_newsletter = False
        self.user.profile.save()

        with patch.object(buttondown_service.client, "patch_subscriber") as mock_patch:
            buttondown_service.sync_user(self.user)

        payload = mock_patch.call_args.args[1]
        self.assertEqual(payload, {"subscriber_type": "unsubscribed"})

    @override_settings(**BD_SETTINGS)
    def test_subsequent_sync_calls_patch_with_correct_id(self):
        with patch.object(buttondown_service.client, "patch_subscriber") as mock_patch:
            buttondown_service.sync_user(self.user)

        subscriber_id_arg = mock_patch.call_args.args[0]
        self.assertEqual(subscriber_id_arg, "bd-uuid-sub")

    @override_settings(**BD_SETTINGS)
    def test_subsequent_sync_touches_last_updated(self):
        original_updated = self.bd_account.last_updated

        with patch.object(buttondown_service.client, "patch_subscriber"):
            buttondown_service.sync_user(self.user)

        self.bd_account.refresh_from_db()
        self.assertGreaterEqual(self.bd_account.last_updated, original_updated)


# ---------------------------------------------------------------------------
# ButtondownService.remove_user
# ---------------------------------------------------------------------------


class ButtondownServiceRemoveUserTests(TestCase):
    @override_settings(**BD_SETTINGS)
    def test_remove_user_calls_delete_subscriber(self):
        with patch.object(
            buttondown_service.client, "delete_subscriber"
        ) as mock_delete:
            buttondown_service.remove_user("bd-uuid-del")

        mock_delete.assert_called_once_with("bd-uuid-del")

    @override_settings(**BD_SETTINGS)
    def test_remove_user_for_user_calls_remove_user(self):
        user = UserFactory.create()
        ButtondownAccount.objects.create(user=user, buttondown_identifier="bd-uuid-del")

        with patch.object(buttondown_service, "remove_user") as mock_remove:
            buttondown_service.remove_user_for_user(user)

        mock_remove.assert_called_once_with("bd-uuid-del")

    @override_settings(**BD_SETTINGS)
    def test_remove_user_for_user_does_nothing_when_no_account(self):
        user = UserFactory.create()

        with patch.object(buttondown_service, "remove_user") as mock_remove:
            buttondown_service.remove_user_for_user(user)

        mock_remove.assert_not_called()


# ---------------------------------------------------------------------------
# sync_user_to_buttondown task
# ---------------------------------------------------------------------------


class SyncUserToButtondownTaskTests(TestCase):
    @override_settings(BUTTONDOWN_API_KEY="")
    def test_skips_when_not_configured(self):
        with patch.object(buttondown_service, "sync_user") as mock_sync:
            sync_user_to_buttondown.call(user_id=999)

        mock_sync.assert_not_called()

    @override_settings(**BD_SETTINGS)
    def test_skips_for_missing_user(self):
        with patch.object(buttondown_service, "sync_user") as mock_sync:
            sync_user_to_buttondown.call(user_id=999999)

        mock_sync.assert_not_called()

    @override_settings(**BD_SETTINGS)
    def test_calls_service_sync_user(self):
        user = UserFactory.create()
        with patch.object(buttondown_service, "sync_user") as mock_sync:
            sync_user_to_buttondown.call(user_id=user.pk)

        mock_sync.assert_called_once()
        self.assertEqual(mock_sync.call_args.args[0].pk, user.pk)

    @override_settings(**BD_SETTINGS)
    def test_handles_service_exception_without_raising(self):
        user = UserFactory.create()
        with patch.object(
            buttondown_service, "sync_user", side_effect=Exception("API down")
        ):
            # Should not raise
            sync_user_to_buttondown.call(user_id=user.pk)


# ---------------------------------------------------------------------------
# remove_user_from_buttondown task
# ---------------------------------------------------------------------------


class RemoveUserFromButtondownTaskTests(TestCase):
    @override_settings(BUTTONDOWN_API_KEY="")
    def test_skips_when_not_configured(self):
        with patch.object(buttondown_service, "remove_user") as mock_remove:
            remove_user_from_buttondown.call(buttondown_identifier="bd-uuid")

        mock_remove.assert_not_called()

    @override_settings(**BD_SETTINGS)
    def test_calls_service_remove_user(self):
        with patch.object(buttondown_service, "remove_user") as mock_remove:
            remove_user_from_buttondown.call(buttondown_identifier="bd-uuid")

        mock_remove.assert_called_once_with("bd-uuid")

    @override_settings(**BD_SETTINGS)
    def test_handles_service_exception_without_raising(self):
        with patch.object(
            buttondown_service, "remove_user", side_effect=Exception("API down")
        ):
            # Should not raise
            remove_user_from_buttondown.call(buttondown_identifier="bd-uuid")


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------


class ButtondownSignalTests(TestCase):
    """
    Signal tests use ImmediateBackend (configured in test settings), so
    enqueued tasks run synchronously. We mock at the service layer to verify
    the full signal→task→service chain fires correctly.
    """

    @override_settings(**BD_SETTINGS)
    def test_profile_save_triggers_sync_when_account_exists(self):
        user = UserFactory.create()
        ButtondownAccount.objects.create(
            user=user, buttondown_identifier="bd-uuid-signal"
        )

        with patch.object(buttondown_service, "sync_user") as mock_sync:
            user.profile.bio = "updated"
            user.profile.save()

        mock_sync.assert_called_once()
        self.assertEqual(mock_sync.call_args.args[0].pk, user.pk)

    @override_settings(**BD_SETTINGS)
    def test_profile_save_always_triggers_sync_when_configured(self):
        user = UserFactory.create()
        # No ButtondownAccount, receiving_newsletter=False — still syncs
        with patch.object(buttondown_service, "sync_user") as mock_sync:
            user.profile.bio = "updated"
            user.profile.save()

        mock_sync.assert_called_once()
        self.assertEqual(mock_sync.call_args.args[0].pk, user.pk)

    @override_settings(**BD_SETTINGS)
    def test_profile_save_triggers_sync_when_opting_in_with_no_account(self):
        user = UserFactory.create()
        # No ButtondownAccount but user opts in — trigger first sync
        with patch.object(buttondown_service, "sync_user") as mock_sync:
            user.profile.receiving_newsletter = True
            user.profile.save()

        mock_sync.assert_called_once()
        self.assertEqual(mock_sync.call_args.args[0].pk, user.pk)

    @override_settings(**BD_SETTINGS)
    def test_new_signup_triggers_sync(self):
        # Create via ORM directly so post_save signals fire (factory mutes them)
        from django.contrib.auth import get_user_model

        User = get_user_model()

        with patch.object(buttondown_service, "sync_user") as mock_sync:
            User.objects.create_user(username="newuser", email="new@example.com")

        mock_sync.assert_called_once()

    @override_settings(BUTTONDOWN_API_KEY="")
    def test_profile_save_does_not_sync_when_not_configured(self):
        user = UserFactory.create()
        ButtondownAccount.objects.create(
            user=user, buttondown_identifier="bd-uuid-signal"
        )

        with patch.object(buttondown_service, "sync_user") as mock_sync:
            user.profile.bio = "updated"
            user.profile.save()

        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# sync_buttondown management command
# ---------------------------------------------------------------------------


class SyncButtondownCommandTests(TestCase):
    """
    Management command tests use ImmediateBackend, so enqueued tasks run
    synchronously. We mock at the service layer to verify correct dispatch.
    """

    @override_settings(**BD_SETTINGS)
    def test_syncs_active_users(self):
        from django.core.management import call_command

        active1 = UserFactory.create(is_active=True)
        active2 = UserFactory.create(is_active=True)
        UserFactory.create(is_active=False)

        with patch.object(buttondown_service, "sync_user") as mock_sync:
            call_command("sync_buttondown", stdout=StringIO(), stderr=StringIO())

        synced_pks = {c.args[0].pk for c in mock_sync.call_args_list}
        self.assertIn(active1.pk, synced_pks)
        self.assertIn(active2.pk, synced_pks)
        self.assertEqual(mock_sync.call_count, 2)

    @override_settings(**BD_SETTINGS)
    def test_dry_run_does_not_sync(self):
        from django.core.management import call_command

        UserFactory.create(is_active=True)

        with patch.object(buttondown_service, "sync_user") as mock_sync:
            out = StringIO()
            call_command("sync_buttondown", dry_run=True, stdout=out, stderr=StringIO())

        mock_sync.assert_not_called()
        self.assertIn("Dry run", out.getvalue())

    @override_settings(BUTTONDOWN_API_KEY="")
    def test_aborts_when_not_configured(self):
        from django.core.management import call_command

        UserFactory.create(is_active=True)

        with patch.object(buttondown_service, "sync_user") as mock_sync:
            err = StringIO()
            call_command("sync_buttondown", stdout=StringIO(), stderr=err)

        mock_sync.assert_not_called()
        self.assertIn("BUTTONDOWN_API_KEY", err.getvalue())
