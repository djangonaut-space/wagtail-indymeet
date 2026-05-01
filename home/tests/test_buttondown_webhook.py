"""Tests for the Buttondown webhook handler."""

import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.factories import UserFactory
from accounts.models import ButtondownAccount, UserProfile
from home.integrations.buttondown import id_translation
from home.integrations.buttondown.service import buttondown_service
from home.integrations.buttondown.webhook import _verify_signature

WEBHOOK_SECRET = "test-webhook-secret"
WEBHOOK_SETTINGS = {"BUTTONDOWN_WEBHOOK_SECRET": WEBHOOK_SECRET}


def _make_signature(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _post(client, payload: dict, secret: str = WEBHOOK_SECRET) -> object:
    body = json.dumps(payload).encode()
    return client.post(
        reverse("buttondown_webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_BUTTONDOWN_SIGNATURE=_make_signature(body, secret),
    )


class VerifySignatureTests(TestCase):
    @override_settings(**WEBHOOK_SETTINGS)
    def test_valid_signature_returns_true(self):
        body = b'{"event_type": "subscriber.unsubscribed"}'
        sig = _make_signature(body)
        self.assertTrue(_verify_signature(body, sig))

    @override_settings(**WEBHOOK_SETTINGS)
    def test_wrong_secret_returns_false(self):
        body = b'{"event_type": "subscriber.unsubscribed"}'
        sig = _make_signature(body, secret="wrong-secret")
        self.assertFalse(_verify_signature(body, sig))

    @override_settings(**WEBHOOK_SETTINGS)
    def test_tampered_body_returns_false(self):
        body = b'{"event_type": "subscriber.unsubscribed"}'
        sig = _make_signature(body)
        self.assertFalse(_verify_signature(b'{"event_type": "other"}', sig))

    @override_settings(**WEBHOOK_SETTINGS)
    def test_missing_sha256_prefix_returns_false(self):
        body = b'{"event_type": "test"}'
        digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        self.assertFalse(_verify_signature(body, digest))  # no "sha256=" prefix

    @override_settings(BUTTONDOWN_WEBHOOK_SECRET="")
    def test_unconfigured_secret_returns_false(self):
        body = b'{"event_type": "test"}'
        sig = _make_signature(body)
        self.assertFalse(_verify_signature(body, sig))

    @override_settings(BUTTONDOWN_WEBHOOK_SECRET=None)
    def test_none_secret_returns_false(self):
        body = b'{"event_type": "test"}'
        sig = _make_signature(body)
        self.assertFalse(_verify_signature(body, sig))


class WebhookEndpointTests(TestCase):
    @override_settings(**WEBHOOK_SETTINGS)
    def test_rejects_invalid_signature(self):
        body = json.dumps({"event_type": "subscriber.unsubscribed"}).encode()
        response = self.client.post(
            reverse("buttondown_webhook"),
            data=body,
            content_type="application/json",
            headers={"x-buttondown-signature": "sha256=badsig"},
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(**WEBHOOK_SETTINGS)
    def test_rejects_missing_signature(self):
        body = json.dumps({"event_type": "subscriber.unsubscribed"}).encode()
        response = self.client.post(
            reverse("buttondown_webhook"),
            data=body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(BUTTONDOWN_WEBHOOK_SECRET="")
    def test_rejects_when_secret_not_configured(self):
        response = _post(self.client, {"event_type": "subscriber.unsubscribed"})
        self.assertEqual(response.status_code, 403)

    @override_settings(**WEBHOOK_SETTINGS)
    def test_rejects_malformed_json(self):
        sig = _make_signature(b"not-json")
        response = self.client.post(
            reverse("buttondown_webhook"),
            data=b"not-json",
            content_type="application/json",
            headers={"x-buttondown-signature": sig},
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(**WEBHOOK_SETTINGS)
    def test_returns_200_for_unknown_event_type(self):
        response = _post(self.client, {"event_type": "subscriber.created", "data": {}})
        self.assertEqual(response.status_code, 200)

    def test_rejects_get_request(self):
        response = self.client.get(reverse("buttondown_webhook"))
        self.assertEqual(response.status_code, 405)

    @override_settings(**WEBHOOK_SETTINGS)
    def test_csrf_exempt(self):
        # Django test client doesn't enforce CSRF by default, but we verify the
        # view is reachable without a CSRF token (no 403 from CSRF middleware).
        body = json.dumps({"event_type": "subscriber.created", "data": {}}).encode()
        response = self.client.post(
            reverse("buttondown_webhook"),
            data=body,
            content_type="application/json",
            headers={"x-buttondown-signature": _make_signature(body)},
            enforce_csrf_checks=True,
        )
        self.assertNotEqual(response.status_code, 403)


class SubscriberUnsubscribedTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.user.profile.receiving_newsletter = True
        self.user.profile.save()
        self.bd_account = ButtondownAccount.objects.create(
            user=self.user, buttondown_identifier="bduuidwebhook"
        )

    def _unsubscribe_payload(self, subscriber_id: str = "bduuidwebhook") -> dict:
        return {
            "event_type": "subscriber.unsubscribed",
            "data": {"subscriber": subscriber_id},
        }

    @override_settings(**WEBHOOK_SETTINGS)
    def test_sets_receiving_newsletter_false(self):
        response = _post(self.client, self._unsubscribe_payload())

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.receiving_newsletter)

    @override_settings(**WEBHOOK_SETTINGS)
    def test_unknown_subscriber_id_returns_200(self):
        response = _post(self.client, self._unsubscribe_payload("unknownsubid"))

        self.assertEqual(response.status_code, 200)
        # Existing user unaffected
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.receiving_newsletter)

    @override_settings(**WEBHOOK_SETTINGS)
    def test_unknown_uuid_subscriber_id_returns_200(self):
        unknown_uuid = "00000000-0000-0000-0000-000000000001"
        response = _post(self.client, self._unsubscribe_payload(unknown_uuid))

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.receiving_newsletter)

    @override_settings(**WEBHOOK_SETTINGS)
    def test_already_unsubscribed_is_no_op(self):
        self.user.profile.receiving_newsletter = False
        self.user.profile.save()

        response = _post(self.client, self._unsubscribe_payload())

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.receiving_newsletter)

    @override_settings(**WEBHOOK_SETTINGS)
    def test_missing_subscriber_id_returns_200(self):
        payload = {"event_type": "subscriber.unsubscribed", "data": {}}
        response = _post(self.client, payload)

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.receiving_newsletter)

    @override_settings(**WEBHOOK_SETTINGS)
    def test_does_not_trigger_sync_signal(self):
        """QuerySet.update() bypasses post_save — no sync task is enqueued."""
        with patch.object(buttondown_service, "sync_user") as mock_sync:
            _post(self.client, self._unsubscribe_payload())

        mock_sync.assert_not_called()

    @override_settings(**WEBHOOK_SETTINGS)
    def test_uuid_subscriber_id_is_translated_to_sub(self):
        """
        Buttondown may send the full UUID form; it should be translated
        to sub_ before lookup.
        """
        known_sub = "sub_43cr6b9qxz9zbr9hes7d36d3zp"
        known_uuid = "83660cb4-dfbf-4fd7-84c5-d93b46668ff6"

        self.bd_account.buttondown_identifier = known_sub
        self.bd_account.save()

        response = _post(self.client, self._unsubscribe_payload(known_uuid))

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.receiving_newsletter)


class IdTranslationTests(TestCase):
    KNOWN_SUB = "sub_5anaxvqk6cvqeyxvqzzynanexv"
    KNOWN_UUID = "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb"

    def test_sub_to_uuid_known_value(self):
        self.assertEqual(id_translation.sub_to_uuid(self.KNOWN_SUB), self.KNOWN_UUID)

    def test_uuid_to_sub_known_value(self):
        self.assertEqual(id_translation.uuid_to_sub(self.KNOWN_UUID), self.KNOWN_SUB)

    def test_sub_to_uuid_round_trip(self):
        result = id_translation.uuid_to_sub(id_translation.sub_to_uuid(self.KNOWN_SUB))
        self.assertEqual(result, self.KNOWN_SUB)

    def test_uuid_to_sub_round_trip(self):
        result = id_translation.sub_to_uuid(id_translation.uuid_to_sub(self.KNOWN_UUID))
        self.assertEqual(result, self.KNOWN_UUID)
