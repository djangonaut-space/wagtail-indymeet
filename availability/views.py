import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic.edit import UpdateView

from availability.forms import UserAvailabilityForm
from availability.models import CalendarConnection, UserAvailability
from availability.providers import google, service
from availability.providers.base import CalendarSyncError
from availability.providers.service import connection_busy_slots
from availability.slots import current_week_window
from availability.tasks import sync_calendar_connection

OAUTH_STATE_SESSION_KEY = "google_calendar_oauth_state"


def _window_label(now=None) -> str:
    """Human label for the concrete week import/overlay uses (e.g. 'Jul 10 – Jul 12')."""
    window_start, window_end, _ = current_week_window(now)
    last_day = window_end - timedelta(days=1)
    return f"{window_start:%b %-d} – {last_day:%b %-d}"


def _google_redirect_uri() -> str:
    """Absolute callback URL registered with Google (stable across requests)."""
    return settings.BASE_URL + reverse("google_calendar_callback")


class UpdateAvailabilityView(LoginRequiredMixin, UpdateView):
    """View for updating user's weekly availability."""

    form_class = UserAvailabilityForm
    template_name = "registration/update_availability.html"

    def get_object(self, queryset=None):
        """Get or create the UserAvailability object for the current user."""
        availability, created = UserAvailability.objects.get_or_create(
            user=self.request.user
        )
        return availability

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["google_configured"] = google.is_configured()
        context["google_connections"] = list(
            self.request.user.calendar_connections.all()
        )
        context["calendar_week_label"] = _window_label()
        return context

    def get_success_url(self):
        messages.add_message(
            self.request,
            messages.SUCCESS,
            "Your availability has been updated successfully.",
        )
        return reverse("profile")


@login_required
def google_calendar_connect(request: HttpRequest) -> HttpResponse:
    """Start the Google OAuth flow: store a CSRF state and redirect to consent."""
    if not google.is_configured():
        messages.error(request, "Google Calendar integration is not configured.")
        return redirect("availability")

    state = secrets.token_urlsafe(32)
    request.session[OAUTH_STATE_SESSION_KEY] = state
    return redirect(google.build_authorization_url(state, _google_redirect_uri()))


@login_required
def google_calendar_callback(request: HttpRequest) -> HttpResponse:
    """Handle Google's OAuth redirect: verify state, exchange code, store tokens."""
    expected_state = request.session.pop(OAUTH_STATE_SESSION_KEY, None)
    error = request.GET.get("error")
    if error:
        messages.error(request, f"Google Calendar connection was cancelled ({error}).")
        return redirect("availability")

    state = request.GET.get("state")
    code = request.GET.get("code")
    if not state or state != expected_state or not code:
        messages.error(
            request, "Could not verify the Google Calendar authorization request."
        )
        return redirect("availability")

    try:
        tokens = google.exchange_code(code, _google_redirect_uri())
    except CalendarSyncError:
        messages.error(
            request, "Connecting your Google Calendar failed. Please try again."
        )
        return redirect("availability")

    access_token = tokens.get("access_token", "")
    email = google.fetch_account_email(access_token) if access_token else ""
    expiry = timezone.now() + timedelta(seconds=int(tokens.get("expires_in", 3600)))

    # The account email uniquely identifies the connection for this user, so
    # re-authorizing the same account refreshes its tokens rather than creating
    # a duplicate; a different account adds a new connection.
    defaults = {
        "access_token": access_token,
        "token_expiry": expiry,
        "scopes": tokens.get("scope", ""),
    }
    # Google only returns a refresh token on the first consent; keep the existing
    # one if this re-auth didn't include a fresh one.
    if tokens.get("refresh_token"):
        defaults["refresh_token"] = tokens["refresh_token"]

    connection, _ = CalendarConnection.objects.update_or_create(
        user=request.user,
        account_label=email,
        defaults=defaults,
    )

    # Pull an initial month of busy times (and register a webhook channel when
    # enabled) in the background so the connection is usable shortly after.
    sync_calendar_connection.enqueue(connection.pk)

    messages.success(
        request,
        f"Connected Google Calendar{f' ({email})' if email else ''}.",
    )
    return redirect("availability")


@login_required
@require_POST
def calendar_disconnect(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove a single calendar connection for the current user."""
    connection = request.user.calendar_connections.filter(pk=pk).first()
    if connection is None:
        messages.success(request, "Calendar disconnected.")
        return redirect("availability")

    # Best-effort: stop the push-notification channel before deleting so Google
    # doesn't keep sending notifications for a connection that no longer exists.
    if connection.webhook_channel_id and connection.webhook_resource_id:
        try:
            service.get_provider(connection).stop_channel(
                connection.webhook_channel_id, connection.webhook_resource_id
            )
        except CalendarSyncError:
            pass

    connection.delete()
    messages.success(request, "Calendar disconnected.")
    return redirect("availability")


@login_required
@require_POST
def calendar_import(request: HttpRequest) -> JsonResponse:
    """Return busy recurring-week slots (current week, from today) across all connections.

    Slots are UTC hours-from-start-of-week floats matching the grid; the frontend
    uses them to deselect conflicting availability cells.
    """
    connections = list(request.user.calendar_connections.all())
    if not connections:
        return JsonResponse(
            {"ok": False, "error": "No Google Calendar is connected."}, status=400
        )

    # Import is an explicit user action, so refresh the cache synchronously to
    # give immediate, up-to-date results before reading the stored busy slots.
    busy_slots: set[float] = set()
    for connection in connections:
        try:
            service.sync_connection(connection)
        except CalendarSyncError:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Could not read your Google Calendar. Please reconnect it.",
                },
                status=502,
            )
        busy_slots |= connection_busy_slots(connection)

    return JsonResponse(
        {
            "ok": True,
            "provider": "Google Calendar",
            "window_label": _window_label(),
            "busy_slots": sorted(busy_slots),
        }
    )


@csrf_exempt
@require_POST
def google_calendar_webhook(request: HttpRequest) -> HttpResponse:
    """Receive Google Calendar push notifications and trigger a re-sync.

    Authenticated by the per-channel token (not a session), so this endpoint is
    CSRF-exempt and verifies the channel id + token. Always returns 200 quickly;
    unknown or invalid notifications are ignored rather than retried.
    """
    channel_id = request.headers.get("X-Goog-Channel-ID", "")
    channel_token = request.headers.get("X-Goog-Channel-Token", "")
    resource_state = request.headers.get("X-Goog-Resource-State", "")

    if not channel_id:
        return HttpResponse(status=200)

    connection = CalendarConnection.objects.filter(
        webhook_channel_id=channel_id
    ).first()
    if connection is None or not hmac.compare_digest(
        channel_token, connection.webhook_channel_token
    ):
        return HttpResponse(status=200)

    # "sync" is Google's initial handshake; "exists" signals a real change.
    if resource_state in {"exists", "sync"}:
        sync_calendar_connection.enqueue(connection.pk)

    return HttpResponse(status=200)
