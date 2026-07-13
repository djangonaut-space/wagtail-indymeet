"""Tests for the calendar integration: encryption, slot mapping, provider,
service layer, and the connect/callback/disconnect/import views."""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.core.management import call_command
from django.db import connection as db_connection
from django.test import override_settings
from django.urls import reverse
from freezegun import freeze_time

from accounts.factories import UserFactory
from availability.factories import CalendarConnectionFactory, UserAvailabilityFactory
from availability.models import CalendarBusyPeriod, CalendarConnection
from availability.providers import google, service
from availability.providers.base import CalendarSyncError
from availability.slots import current_week_window, intervals_to_slots
from availability.tasks import refresh_stale_connections

UTC = dt_timezone.utc


# --------------------------------------------------------------------------- #
# Encrypted field
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_tokens_are_encrypted_at_rest_but_readable():
    conn = CalendarConnectionFactory.create(
        refresh_token="super-secret-refresh", access_token="secret-access"
    )

    # Reading back through the ORM transparently decrypts.
    reloaded = CalendarConnection.objects.get(pk=conn.pk)
    assert reloaded.refresh_token == "super-secret-refresh"
    assert reloaded.access_token == "secret-access"

    # The raw column value is ciphertext, not the plaintext token.
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT refresh_token FROM availability_calendarconnection WHERE id = %s",
            [conn.pk],
        )
        raw_value = cursor.fetchone()[0]
    assert raw_value != "super-secret-refresh"
    assert "super-secret-refresh" not in raw_value


@pytest.mark.django_db
def test_blank_encrypted_field_roundtrips():
    conn = CalendarConnectionFactory.create(refresh_token="")
    assert CalendarConnection.objects.get(pk=conn.pk).refresh_token == ""


# --------------------------------------------------------------------------- #
# Slot mapping
# --------------------------------------------------------------------------- #
@freeze_time("2026-07-08 12:00:00")  # a Wednesday
def test_current_week_window():
    window_start, window_end, week_start = current_week_window()
    assert week_start == datetime(2026, 7, 5, tzinfo=UTC)  # Sunday
    assert window_start == datetime(2026, 7, 8, tzinfo=UTC)  # today 00:00
    assert window_end == datetime(2026, 7, 12, tzinfo=UTC)  # next Sunday


def test_intervals_to_slots_maps_busy_to_recurring_slots():
    week_start = datetime(2026, 7, 5, tzinfo=UTC)  # Sunday
    window_start = datetime(2026, 7, 8, tzinfo=UTC)  # Wednesday (day 3)
    # Busy Wed 14:00-15:00 UTC -> day 3 -> 72 + 14 = 86.0, plus 86.5
    intervals = [
        (
            datetime(2026, 7, 8, 14, 0, tzinfo=UTC),
            datetime(2026, 7, 8, 15, 0, tzinfo=UTC),
        )
    ]
    assert intervals_to_slots(intervals, week_start, window_start) == {86.0, 86.5}


def test_intervals_before_window_start_are_ignored():
    week_start = datetime(2026, 7, 5, tzinfo=UTC)
    window_start = datetime(2026, 7, 8, tzinfo=UTC)  # today = Wednesday
    # Monday event is earlier in the week than "today" -> not imported.
    intervals = [
        (
            datetime(2026, 7, 6, 9, 0, tzinfo=UTC),
            datetime(2026, 7, 6, 10, 0, tzinfo=UTC),
        )
    ]
    assert intervals_to_slots(intervals, week_start, window_start) == set()


def test_partial_slot_overlap_marks_touched_slots():
    week_start = datetime(2026, 7, 5, tzinfo=UTC)
    window_start = datetime(2026, 7, 5, tzinfo=UTC)
    # Sunday 00:10-00:40 touches the 00:00 and 00:30 slots (0.0 and 0.5).
    intervals = [
        (
            datetime(2026, 7, 5, 0, 10, tzinfo=UTC),
            datetime(2026, 7, 5, 0, 40, tzinfo=UTC),
        )
    ]
    assert intervals_to_slots(intervals, week_start, window_start) == {0.0, 0.5}


# --------------------------------------------------------------------------- #
# Google provider
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, *, ok=True, status_code=200, payload=None):
        self.ok = ok
        self.status_code = status_code
        self._payload = payload or {}
        self.text = ""

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._response

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._response


@pytest.mark.django_db
def test_google_provider_parses_freebusy(mocker):
    conn = CalendarConnectionFactory.create(
        access_token="valid-token",
        token_expiry=datetime(2026, 7, 8, 13, 0, tzinfo=UTC),
    )
    response = _FakeResponse(
        payload={
            "calendars": {
                "primary": {
                    "busy": [
                        {"start": "2026-07-08T14:00:00Z", "end": "2026-07-08T15:00:00Z"}
                    ]
                }
            }
        }
    )
    mocker.patch.object(google, "_session", return_value=_FakeSession(response))

    with freeze_time("2026-07-08 12:00:00"):
        provider = google.GoogleCalendarProvider(conn)
        intervals = provider.get_busy_intervals(
            datetime(2026, 7, 8, tzinfo=UTC), datetime(2026, 7, 12, tzinfo=UTC)
        )
    assert intervals == [
        (datetime(2026, 7, 8, 14, tzinfo=UTC), datetime(2026, 7, 8, 15, tzinfo=UTC))
    ]


@pytest.mark.django_db
def test_google_provider_refreshes_expired_token(mocker):
    conn = CalendarConnectionFactory.create(
        access_token="old-token",
        refresh_token="refresh-me",
        token_expiry=datetime(2026, 7, 8, 11, 0, tzinfo=UTC),  # expired
    )
    token_response = _FakeResponse(
        payload={"access_token": "fresh-token", "expires_in": 3600}
    )
    fake_session = _FakeSession(token_response)
    mocker.patch.object(google, "_session", return_value=fake_session)

    with freeze_time("2026-07-08 12:00:00"):
        token = google.GoogleCalendarProvider(conn)._access_token()

    assert token == "fresh-token"
    conn.refresh_from_db()
    assert conn.access_token == "fresh-token"


@pytest.mark.django_db
def test_google_provider_raises_on_error(mocker):
    conn = CalendarConnectionFactory.create(
        access_token="valid", token_expiry=datetime(2030, 1, 1, tzinfo=UTC)
    )
    mocker.patch.object(
        google,
        "_session",
        return_value=_FakeSession(_FakeResponse(ok=False, status_code=500)),
    )
    with pytest.raises(CalendarSyncError):
        google.GoogleCalendarProvider(conn).get_busy_intervals(
            datetime(2026, 7, 8, tzinfo=UTC), datetime(2026, 7, 12, tzinfo=UTC)
        )


# --------------------------------------------------------------------------- #
# Service layer
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_effective_slots_subtracts_busy():
    assert service.effective_slots([0.0, 0.5, 1.0], {0.5}) == [0.0, 1.0]


# --------------------------------------------------------------------------- #
# Sync + cached busy periods
# --------------------------------------------------------------------------- #
@freeze_time("2026-07-08 12:00:00")  # Wednesday
@pytest.mark.django_db
def test_sync_connection_stores_prunes_and_records_metadata(mocker):
    conn = CalendarConnectionFactory.create()
    # An old period (ends >1 week ago) should be pruned.
    old = CalendarBusyPeriod.objects.create(
        connection=conn,
        start=datetime(2026, 6, 19, 9, tzinfo=UTC),
        end=datetime(2026, 6, 19, 10, tzinfo=UTC),
    )
    provider = mocker.Mock()
    provider.get_busy_intervals.return_value = [
        (datetime(2026, 7, 8, 14, tzinfo=UTC), datetime(2026, 7, 8, 15, tzinfo=UTC))
    ]
    mocker.patch.object(service, "get_provider", return_value=provider)

    service.sync_connection(conn)

    assert not CalendarBusyPeriod.objects.filter(pk=old.pk).exists()
    stored = list(conn.busy_periods.values_list("start", "end"))
    assert stored == [
        (datetime(2026, 7, 8, 14, tzinfo=UTC), datetime(2026, 7, 8, 15, tzinfo=UTC))
    ]
    conn.refresh_from_db()
    assert conn.last_synced_at == datetime(2026, 7, 8, 12, tzinfo=UTC)
    assert conn.synced_until == datetime(2026, 7, 8, 12, tzinfo=UTC) + timedelta(
        days=30
    )
    assert conn.last_sync_error == ""


@freeze_time("2026-07-08 12:00:00")
@pytest.mark.django_db
def test_sync_connection_fetches_month_horizon(mocker):
    conn = CalendarConnectionFactory.create()
    provider = mocker.Mock()
    provider.get_busy_intervals.return_value = []
    mocker.patch.object(service, "get_provider", return_value=provider)

    service.sync_connection(conn)

    (start, end), _ = provider.get_busy_intervals.call_args
    assert start == datetime(2026, 7, 8, tzinfo=UTC)  # start of today
    assert end == datetime(2026, 7, 8, 12, tzinfo=UTC) + timedelta(days=30)


@pytest.mark.django_db
def test_sync_connection_error_preserves_existing_and_records_error(mocker):
    conn = CalendarConnectionFactory.create()
    existing = CalendarBusyPeriod.objects.create(
        connection=conn,
        start=datetime(2030, 1, 1, 9, tzinfo=UTC),
        end=datetime(2030, 1, 1, 10, tzinfo=UTC),
    )
    provider = mocker.Mock()
    provider.get_busy_intervals.side_effect = CalendarSyncError("boom")
    mocker.patch.object(service, "get_provider", return_value=provider)

    with pytest.raises(CalendarSyncError):
        service.sync_connection(conn)

    assert CalendarBusyPeriod.objects.filter(pk=existing.pk).exists()
    conn.refresh_from_db()
    assert conn.last_sync_error == "boom"
    assert conn.last_synced_at is None


@freeze_time("2026-07-08 12:00:00")
@pytest.mark.django_db
def test_connection_busy_slots_reads_db_without_provider(mocker):
    conn = CalendarConnectionFactory.create()
    CalendarBusyPeriod.objects.create(
        connection=conn,
        start=datetime(2026, 7, 8, 14, tzinfo=UTC),
        end=datetime(2026, 7, 8, 15, tzinfo=UTC),
    )
    get_provider = mocker.patch.object(service, "get_provider")

    assert service.connection_busy_slots(conn) == {86.0, 86.5}
    get_provider.assert_not_called()


@override_settings(
    GOOGLE_CALENDAR_WEBHOOK_ENABLED=True,
    GOOGLE_OAUTH_CLIENT_ID="client-id",
    GOOGLE_OAUTH_CLIENT_SECRET="secret",
    BASE_URL="https://example.test",
)
@freeze_time("2026-07-08 12:00:00")
@pytest.mark.django_db
def test_sync_connection_registers_webhook_channel_when_enabled(mocker):
    conn = CalendarConnectionFactory.create()
    provider = mocker.Mock()
    provider.get_busy_intervals.return_value = []
    provider.watch_events.return_value = {
        "resource_id": "res-1",
        "expiration": datetime(2026, 7, 15, tzinfo=UTC),
    }
    mocker.patch.object(service, "get_provider", return_value=provider)

    service.sync_connection(conn)

    provider.watch_events.assert_called_once()
    conn.refresh_from_db()
    assert conn.webhook_channel_id
    assert conn.webhook_resource_id == "res-1"
    assert conn.webhook_channel_token  # shared secret persisted
    assert conn.webhook_expires_at == datetime(2026, 7, 15, tzinfo=UTC)


@freeze_time("2026-07-08 12:00:00")
@pytest.mark.django_db
def test_sync_connection_skips_webhook_when_disabled(mocker):
    conn = CalendarConnectionFactory.create()
    provider = mocker.Mock()
    provider.get_busy_intervals.return_value = []
    mocker.patch.object(service, "get_provider", return_value=provider)

    service.sync_connection(conn)

    provider.watch_events.assert_not_called()


@freeze_time("2026-07-08 12:00:00")
@pytest.mark.django_db
def test_refresh_stale_connections_enqueues_only_stale(mocker):
    # Which connections count as stale is unit-tested against the ORM in
    # test_managers.py; this checks the task enqueues a sync for exactly those.
    user = UserFactory.create()
    fresh = CalendarConnectionFactory.create(
        user=user,
        account_label="fresh@example.com",
        last_synced_at=datetime(2026, 7, 8, 11, 59, tzinfo=UTC),  # minutes ago
    )
    stale = CalendarConnectionFactory.create(
        user=user,
        account_label="stale@example.com",
        last_synced_at=datetime(2026, 7, 8, 0, 0, tzinfo=UTC),  # 12h ago
    )
    task = mocker.patch("availability.tasks.sync_calendar_connection")

    refresh_stale_connections(user)

    enqueued = {call.args[0] for call in task.enqueue.call_args_list}
    assert enqueued == {stale.pk}
    assert fresh.pk not in enqueued


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
@override_settings(
    GOOGLE_OAUTH_CLIENT_ID="client-id",
    GOOGLE_OAUTH_CLIENT_SECRET="secret",
    BASE_URL="https://example.test",
)
@pytest.mark.django_db
def test_connect_redirects_to_google_and_stores_state(client):
    user = UserFactory.create()
    client.force_login(user)
    response = client.get(reverse("google_calendar_connect"))
    assert response.status_code == 302
    assert response.url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert client.session["google_calendar_oauth_state"] in response.url


@pytest.mark.django_db
def test_callback_creates_connection(client, mocker):
    user = UserFactory.create()
    client.force_login(user)
    session = client.session
    session["google_calendar_oauth_state"] = "state-123"
    session.save()

    mocker.patch.object(
        google,
        "exchange_code",
        return_value={
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
            "scope": "openid email",
        },
    )
    mocker.patch.object(google, "fetch_account_email", return_value="me@example.com")

    response = client.get(
        reverse("google_calendar_callback"), {"state": "state-123", "code": "abc"}
    )
    assert response.status_code == 302
    conn = CalendarConnection.objects.get(user=user, account_label="me@example.com")
    assert conn.refresh_token == "rt"


@pytest.mark.django_db
def test_callback_reconnecting_same_account_updates_in_place(client, mocker):
    user = UserFactory.create()
    client.force_login(user)
    session = client.session
    session["google_calendar_oauth_state"] = "state-123"
    session.save()

    mocker.patch.object(
        google,
        "exchange_code",
        return_value={"access_token": "at2", "expires_in": 3600, "scope": "email"},
    )
    mocker.patch.object(google, "fetch_account_email", return_value="me@example.com")
    CalendarConnectionFactory.create(
        user=user, account_label="me@example.com", refresh_token="original-refresh"
    )

    client.get(
        reverse("google_calendar_callback"), {"state": "state-123", "code": "abc"}
    )

    conn = CalendarConnection.objects.get(user=user)
    assert conn.access_token == "at2"
    # No refresh token in the re-auth response keeps the original one.
    assert conn.refresh_token == "original-refresh"


@pytest.mark.django_db
def test_callback_different_account_adds_second_connection(client, mocker):
    user = UserFactory.create()
    client.force_login(user)
    session = client.session
    session["google_calendar_oauth_state"] = "state-123"
    session.save()

    mocker.patch.object(
        google,
        "exchange_code",
        return_value={"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
    )
    mocker.patch.object(
        google, "fetch_account_email", return_value="second@example.com"
    )
    CalendarConnectionFactory.create(user=user, account_label="first@example.com")

    client.get(
        reverse("google_calendar_callback"), {"state": "state-123", "code": "abc"}
    )

    labels = set(
        CalendarConnection.objects.filter(user=user).values_list(
            "account_label", flat=True
        )
    )
    assert labels == {"first@example.com", "second@example.com"}


@pytest.mark.django_db
def test_callback_rejects_bad_state(client):
    user = UserFactory.create()
    client.force_login(user)
    session = client.session
    session["google_calendar_oauth_state"] = "expected"
    session.save()

    response = client.get(
        reverse("google_calendar_callback"), {"state": "wrong", "code": "abc"}
    )
    assert response.status_code == 302
    assert not CalendarConnection.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_disconnect_removes_single_connection(client):
    user = UserFactory.create()
    kept = CalendarConnectionFactory.create(user=user, account_label="keep@example.com")
    removed = CalendarConnectionFactory.create(
        user=user, account_label="drop@example.com"
    )
    client.force_login(user)

    response = client.post(reverse("calendar_disconnect", args=[removed.pk]))
    assert response.status_code == 302
    remaining = CalendarConnection.objects.filter(user=user)
    assert list(remaining) == [kept]


@pytest.mark.django_db
def test_import_syncs_then_returns_busy_slots(client, mocker):
    user = UserFactory.create()
    UserAvailabilityFactory.create(user=user, slots=[86.0, 86.5, 90.0])
    CalendarConnectionFactory.create(user=user)
    client.force_login(user)

    sync = mocker.patch("availability.providers.service.sync_connection")
    mocker.patch("availability.views.connection_busy_slots", return_value={86.0, 86.5})
    response = client.post(reverse("calendar_import"))
    data = response.json()
    assert data["ok"] is True
    assert data["busy_slots"] == [86.0, 86.5]
    assert data["provider"] == "Google Calendar"
    sync.assert_called_once()


@pytest.mark.django_db
def test_import_returns_502_when_sync_fails(client, mocker):
    user = UserFactory.create()
    CalendarConnectionFactory.create(user=user)
    client.force_login(user)

    mocker.patch(
        "availability.providers.service.sync_connection",
        side_effect=CalendarSyncError("boom"),
    )
    response = client.post(reverse("calendar_import"))
    assert response.status_code == 502
    assert response.json()["ok"] is False


@pytest.mark.django_db
def test_import_without_connection_returns_400(client):
    user = UserFactory.create()
    client.force_login(user)
    response = client.post(reverse("calendar_import"))
    assert response.status_code == 400
    assert response.json()["ok"] is False


# --------------------------------------------------------------------------- #
# Webhook + channel lifecycle + polling command
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_webhook_enqueues_sync_for_valid_channel(client, mocker):
    conn = CalendarConnectionFactory.create(
        webhook_channel_id="chan-1", webhook_channel_token="tok-1"
    )
    task = mocker.patch("availability.views.sync_calendar_connection")

    response = client.post(
        reverse("google_calendar_webhook"),
        HTTP_X_GOOG_CHANNEL_ID="chan-1",
        HTTP_X_GOOG_CHANNEL_TOKEN="tok-1",
        HTTP_X_GOOG_RESOURCE_STATE="exists",
    )
    assert response.status_code == 200
    task.enqueue.assert_called_once_with(conn.pk)


@pytest.mark.django_db
def test_webhook_ignores_bad_token(client, mocker):
    CalendarConnectionFactory.create(
        webhook_channel_id="chan-1", webhook_channel_token="tok-1"
    )
    task = mocker.patch("availability.views.sync_calendar_connection")

    response = client.post(
        reverse("google_calendar_webhook"),
        HTTP_X_GOOG_CHANNEL_ID="chan-1",
        HTTP_X_GOOG_CHANNEL_TOKEN="wrong",
        HTTP_X_GOOG_RESOURCE_STATE="exists",
    )
    assert response.status_code == 200
    task.enqueue.assert_not_called()


@pytest.mark.django_db
def test_webhook_ignores_unknown_channel(client, mocker):
    task = mocker.patch("availability.views.sync_calendar_connection")

    response = client.post(
        reverse("google_calendar_webhook"),
        HTTP_X_GOOG_CHANNEL_ID="does-not-exist",
        HTTP_X_GOOG_CHANNEL_TOKEN="whatever",
        HTTP_X_GOOG_RESOURCE_STATE="exists",
    )
    assert response.status_code == 200
    task.enqueue.assert_not_called()


@pytest.mark.django_db
def test_disconnect_stops_webhook_channel(client, mocker):
    user = UserFactory.create()
    conn = CalendarConnectionFactory.create(
        user=user, webhook_channel_id="chan-1", webhook_resource_id="res-1"
    )
    provider = mocker.Mock()
    mocker.patch.object(service, "get_provider", return_value=provider)
    client.force_login(user)

    client.post(reverse("calendar_disconnect", args=[conn.pk]))

    provider.stop_channel.assert_called_once_with("chan-1", "res-1")
    assert not CalendarConnection.objects.filter(pk=conn.pk).exists()


@freeze_time("2026-07-08 12:00:00")
@pytest.mark.django_db
def test_sync_calendars_command_enqueues_and_prunes(mocker):
    conn = CalendarConnectionFactory.create()
    old = CalendarBusyPeriod.objects.create(
        connection=conn,
        start=datetime(2026, 6, 1, 9, tzinfo=UTC),
        end=datetime(2026, 6, 1, 10, tzinfo=UTC),
    )
    task = mocker.patch(
        "availability.management.commands.sync_calendars.sync_calendar_connection"
    )

    call_command("sync_calendars")

    task.enqueue.assert_called_once_with(conn.pk)
    assert not CalendarBusyPeriod.objects.filter(pk=old.pk).exists()
