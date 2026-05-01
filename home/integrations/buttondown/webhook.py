import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import ButtondownAccount, UserProfile

logger = logging.getLogger(__name__)


def _verify_signature(body: bytes, signature_header: str) -> bool:
    """
    Verify a Buttondown webhook signature.

    Buttondown sends 'X-Buttondown-Signature: sha256=<hexdigest>'
    computed over the raw request body using the webhook secret.
    """
    secret = settings.BUTTONDOWN_WEBHOOK_SECRET
    if not secret:
        return False

    if not signature_header.startswith("sha256="):
        return False

    provided = signature_header[len("sha256=") :]
    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(provided, expected)


def _handle_unsubscribed(payload: dict) -> None:
    """Set receiving_newsletter=False for the unsubscribed subscriber."""
    subscriber_id = (payload.get("data") or {}).get("subscriber", "")
    if not subscriber_id:
        logger.warning("subscriber.unsubscribed webhook missing subscriber ID")
        return

    try:
        bd_account = ButtondownAccount.objects.get(buttondown_identifier=subscriber_id)
    except ButtondownAccount.DoesNotExist:
        logger.info(
            "subscriber.unsubscribed for unknown subscriber %s; ignoring",
            subscriber_id,
        )
        return

    # QuerySet.update() bypasses post_save so the signal doesn't enqueue
    # a redundant sync back to Buttondown.
    updated = UserProfile.objects.filter(
        user=bd_account.user,
        receiving_newsletter=True,
    ).update(receiving_newsletter=False)

    if updated:
        logger.info(
            "Set receiving_newsletter=False for user %s via Buttondown webhook",
            bd_account.user_id,
        )


@csrf_exempt
@require_POST
def buttondown_webhook(request: HttpRequest) -> HttpResponse:
    """
    Handle incoming Buttondown webhook events.

    Handles subscriber.unsubscribed by setting UserProfile.receiving_newsletter=False.
    All requests are verified against BUTTONDOWN_WEBHOOK_SECRET before processing.
    """
    signature = request.headers.get("X-Buttondown-Signature", "")
    if not _verify_signature(request.body, signature):
        return HttpResponseForbidden("Invalid signature")

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    print("Received payload: %s", payload)

    event_type = payload.get("event_type", "")

    match event_type:
        case "subscriber.unsubscribed":
            _handle_unsubscribed(payload)

    return HttpResponse(status=200)
