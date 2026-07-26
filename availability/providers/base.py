from abc import ABC, abstractmethod
from datetime import datetime


class CalendarSyncError(Exception):
    """Raised when busy times cannot be retrieved from a calendar provider."""


class CalendarProvider(ABC):
    """Interface for reading a user's busy times from an external calendar.

    Implementations translate a provider-specific API into a normalized list of
    ``(start, end)`` UTC datetime intervals during which the user is busy.
    """

    def __init__(self, connection) -> None:
        self.connection = connection

    @abstractmethod
    def get_busy_intervals(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        """Return busy intervals overlapping ``[start, end)`` as UTC datetimes."""
        raise NotImplementedError
