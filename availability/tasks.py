"""Background tasks for keeping cached calendar busy data fresh."""

import logging

from django_tasks import task

from availability.models import CalendarConnection
from availability.providers import service
from availability.providers.base import CalendarSyncError

logger = logging.getLogger(__name__)


@task()
def sync_calendar_connection(connection_id: int) -> None:
    """Refresh a single calendar connection's cached busy periods.

    Errors are swallowed (and logged) so a flaky calendar never fails the task;
    the error is recorded on the connection by :func:`service.sync_connection`.
    """
    try:
        connection = CalendarConnection.objects.get(pk=connection_id)
    except CalendarConnection.DoesNotExist:
        return

    try:
        service.sync_connection(connection)
    except CalendarSyncError:
        logger.warning(
            "Calendar sync failed for connection %s", connection_id, exc_info=True
        )


def refresh_stale_connections(user) -> None:
    """Enqueue background syncs for the user's connections with stale cached data."""
    for connection in service.stale_connections(user):
        sync_calendar_connection.enqueue(connection.pk)


def refresh_stale_connections_bulk(users) -> None:
    """Enqueue background syncs for stale connections across many users at once."""
    for connection in service.stale_connections_bulk(users):
        sync_calendar_connection.enqueue(connection.pk)
