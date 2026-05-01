"""Tests for the Buttondown webhook handler."""

import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.factories import UserFactory
from accounts.models import ButtondownAccount, UserProfile
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
            user=self.user, buttondown_identifier="bd-uuid-webhook"
        )

    def _unsubscribe_payload(self, subscriber_id: str = "bd-uuid-webhook") -> dict:
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
        response = _post(self.client, self._unsubscribe_payload("unknown-uuid"))

        self.assertEqual(response.status_code, 200)
        # Existing user unaffected
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
