"""Unit tests for the availability QuerySet/manager methods.

These exercise the ORM-layer filters directly (rather than through the service
functions that call them) so the "overlapping", "stale", and "ending
before/after" rules are pinned down at the database boundary.
"""

from datetime import datetime
from datetime import timezone as dt_timezone

import pytest

from accounts.factories import UserFactory
from availability.factories import CalendarConnectionFactory
from availability.models import CalendarBusyPeriod, CalendarConnection

UTC = dt_timezone.utc


def _period(connection, start, end):
    return CalendarBusyPeriod.objects.create(
        connection=connection, start=start, end=end
    )


# --------------------------------------------------------------------------- #
# CalendarBusyPeriodQuerySet.overlapping
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_overlapping_returns_only_touching_periods():
    conn = CalendarConnectionFactory.create()
    window_start = datetime(2026, 7, 8, tzinfo=UTC)
    window_end = datetime(2026, 7, 12, tzinfo=UTC)

    inside = _period(
        conn, datetime(2026, 7, 9, 10, tzinfo=UTC), datetime(2026, 7, 9, 11, tzinfo=UTC)
    )
    straddle_start = _period(
        conn, datetime(2026, 7, 7, 23, tzinfo=UTC), datetime(2026, 7, 8, 1, tzinfo=UTC)
    )
    straddle_end = _period(
        conn,
        datetime(2026, 7, 11, 23, tzinfo=UTC),
        datetime(2026, 7, 12, 1, tzinfo=UTC),
    )
    # Excluded: fully before, fully after, and the two that merely abut the edges.
    _period(
        conn, datetime(2026, 7, 5, 10, tzinfo=UTC), datetime(2026, 7, 5, 11, tzinfo=UTC)
    )
    _period(
        conn,
        datetime(2026, 7, 12, 10, tzinfo=UTC),
        datetime(2026, 7, 12, 11, tzinfo=UTC),
    )
    _period(  # ends exactly at window_start
        conn, datetime(2026, 7, 7, 23, tzinfo=UTC), window_start
    )
    _period(  # starts exactly at window_end
        conn, window_end, datetime(2026, 7, 12, 1, tzinfo=UTC)
    )

    result = set(
        CalendarBusyPeriod.objects.overlapping(window_start, window_end).values_list(
            "pk", flat=True
        )
    )
    assert result == {inside.pk, straddle_start.pk, straddle_end.pk}


@pytest.mark.django_db
def test_overlapping_is_available_on_the_related_manager():
    """The service layer calls ``connection.busy_periods.overlapping(...)``."""
    conn = CalendarConnectionFactory.create()
    window_start = datetime(2026, 7, 8, tzinfo=UTC)
    window_end = datetime(2026, 7, 12, tzinfo=UTC)
    inside = _period(
        conn, datetime(2026, 7, 9, 10, tzinfo=UTC), datetime(2026, 7, 9, 11, tzinfo=UTC)
    )
    _period(
        conn, datetime(2026, 7, 5, 10, tzinfo=UTC), datetime(2026, 7, 5, 11, tzinfo=UTC)
    )

    result = list(conn.busy_periods.overlapping(window_start, window_end))
    assert result == [inside]


# --------------------------------------------------------------------------- #
# CalendarBusyPeriodQuerySet.for_users
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_for_users_scopes_periods_to_given_users():
    user_a = UserFactory.create()
    user_b = UserFactory.create()
    user_c = UserFactory.create()
    conn_a = CalendarConnectionFactory.create(user=user_a)
    conn_b = CalendarConnectionFactory.create(user=user_b)
    conn_c = CalendarConnectionFactory.create(user=user_c)
    start = datetime(2026, 7, 9, 10, tzinfo=UTC)
    end = datetime(2026, 7, 9, 11, tzinfo=UTC)
    period_a = _period(conn_a, start, end)
    period_b = _period(conn_b, start, end)
    _period(conn_c, start, end)

    result = set(
        CalendarBusyPeriod.objects.for_users([user_a, user_b]).values_list(
            "pk", flat=True
        )
    )
    assert result == {period_a.pk, period_b.pk}


# --------------------------------------------------------------------------- #
# CalendarBusyPeriodQuerySet.ending_after / ending_before
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_ending_after_and_before_split_on_end_time():
    conn = CalendarConnectionFactory.create()
    moment = datetime(2026, 7, 8, 12, tzinfo=UTC)
    ends_earlier = _period(
        conn, datetime(2026, 7, 8, 9, tzinfo=UTC), datetime(2026, 7, 8, 10, tzinfo=UTC)
    )
    ends_later = _period(
        conn, datetime(2026, 7, 8, 13, tzinfo=UTC), datetime(2026, 7, 8, 14, tzinfo=UTC)
    )
    # A period ending exactly at ``moment`` is in neither set (both are strict).
    ends_at_moment = _period(conn, datetime(2026, 7, 8, 11, tzinfo=UTC), moment)

    after = set(
        CalendarBusyPeriod.objects.ending_after(moment).values_list("pk", flat=True)
    )
    before = set(
        CalendarBusyPeriod.objects.ending_before(moment).values_list("pk", flat=True)
    )
    assert after == {ends_later.pk}
    assert before == {ends_earlier.pk}
    assert ends_at_moment.pk not in after
    assert ends_at_moment.pk not in before


# --------------------------------------------------------------------------- #
# CalendarConnectionQuerySet.stale
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_stale_returns_never_synced_and_older_than_cutoff():
    user = UserFactory.create()
    cutoff = datetime(2026, 7, 8, 6, tzinfo=UTC)
    never = CalendarConnectionFactory.create(
        user=user, account_label="never@example.com", last_synced_at=None
    )
    old = CalendarConnectionFactory.create(
        user=user,
        account_label="old@example.com",
        last_synced_at=datetime(2026, 7, 8, 0, tzinfo=UTC),
    )
    fresh = CalendarConnectionFactory.create(
        user=user,
        account_label="fresh@example.com",
        last_synced_at=datetime(2026, 7, 8, 11, tzinfo=UTC),
    )
    # A connection synced exactly at the cutoff is not stale (strict less-than).
    at_cutoff = CalendarConnectionFactory.create(
        user=user, account_label="edge@example.com", last_synced_at=cutoff
    )

    result = set(CalendarConnection.objects.stale(cutoff).values_list("pk", flat=True))
    assert result == {never.pk, old.pk}
    assert fresh.pk not in result
    assert at_cutoff.pk not in result


@pytest.mark.django_db
def test_stale_is_available_on_the_related_manager():
    """The service layer calls ``user.calendar_connections.stale(...)``."""
    user = UserFactory.create()
    cutoff = datetime(2026, 7, 8, 6, tzinfo=UTC)
    stale_conn = CalendarConnectionFactory.create(
        user=user, account_label="stale@example.com", last_synced_at=None
    )
    CalendarConnectionFactory.create(
        user=user,
        account_label="fresh@example.com",
        last_synced_at=datetime(2026, 7, 8, 11, tzinfo=UTC),
    )

    result = list(user.calendar_connections.stale(cutoff))
    assert result == [stale_conn]


# --------------------------------------------------------------------------- #
# CalendarConnectionQuerySet.for_users
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_for_users_scopes_connections_to_given_users():
    user_a = UserFactory.create()
    user_b = UserFactory.create()
    conn_a = CalendarConnectionFactory.create(user=user_a)
    CalendarConnectionFactory.create(user=user_b)

    result = list(CalendarConnection.objects.for_users([user_a]))
    assert result == [conn_a]


@pytest.mark.django_db
def test_for_users_and_stale_compose():
    """``stale_connections_bulk`` chains ``for_users`` then ``stale``."""
    user_a = UserFactory.create()
    user_b = UserFactory.create()
    cutoff = datetime(2026, 7, 8, 6, tzinfo=UTC)
    stale_a = CalendarConnectionFactory.create(
        user=user_a, account_label="a@example.com", last_synced_at=None
    )
    CalendarConnectionFactory.create(
        user=user_a,
        account_label="fresh-a@example.com",
        last_synced_at=datetime(2026, 7, 8, 11, tzinfo=UTC),
    )
    # user_b is stale but excluded because it is outside the user set.
    CalendarConnectionFactory.create(
        user=user_b, account_label="b@example.com", last_synced_at=None
    )

    result = list(CalendarConnection.objects.for_users([user_a]).stale(cutoff))
    assert result == [stale_a]
