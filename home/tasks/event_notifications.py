"""Background tasks for sending event-related notification emails."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_tasks import task

from home import email
from home.icalendar_utils import generate_icalendar
from home.models import Event, EventCalendarInvite


def _record_pending_invites(event: Event) -> None:
    """Record an invite for every recipient of the event not yet emailed.

    Recipients are resolved here rather than once up front, so a later send
    picks up people who joined the session in the meantime. A recipient whose
    invite is already queued conflicts with the per-event unique constraint
    and keeps the invite they have.
    """
    users = {user.email.lower(): user for user in event.get_calendar_invite_users()}
    EventCalendarInvite.objects.bulk_create(
        [
            EventCalendarInvite(
                event=event, email=address, user=users.get(address.lower())
            )
            for address in event.pending_calendar_invite_recipients()
        ],
        ignore_conflicts=True,
    )


@task()
def send_event_calendar_invite(event_id: int) -> None:
    """Fan out an event's calendar invites, one email per recipient.

    Each recipient is mailed by its own task, so one bad address or a retry
    can't affect anybody else's invite. Every invite not yet emailed is
    (re)scheduled, which picks up both people who joined the session since the
    last send and invites whose send never ran. Scheduling one twice is
    harmless: each send locks its invite and re-checks that it is unsent.

    The invites and the sends queued for them commit together, so a failure
    part way through leaves neither behind.

    Args:
        event_id: The ID of the Event to send invites for.
    """
    with transaction.atomic():
        event = Event.objects.filter(pk=event_id).first()
        if event is None:
            return

        _record_pending_invites(event)
        for invite_id in event.calendar_invites.unsent().values_list("id", flat=True):
            send_calendar_invite_email.enqueue(invite_id=invite_id)


@task()
def send_calendar_invite_email(invite_id: int) -> None:
    """Email one recipient their calendar invite and record the delivery.

    Idempotent per recipient: the invite is locked and re-checked as unsent,
    so neither a repeated fan-out nor a concurrent worker can email the same
    person twice.

    Args:
        invite_id: The ID of the EventCalendarInvite to send.
    """
    with transaction.atomic():
        invite = (
            EventCalendarInvite.objects.unsent()
            # Only the invite row: user is nullable, and Postgres can't lock
            # across the nullable side of the resulting outer join.
            .select_for_update(of=("self",))
            .select_related("event", "user")
            .filter(pk=invite_id)
            .first()
        )
        if invite is None:
            return

        event = invite.event
        ical_data = generate_icalendar(event)
        email.send(
            from_email=settings.SESSIONS_FROM_EMAIL,
            email_template="event_calendar_invite",
            recipient_list=[invite.email],
            context={
                "event": event,
                "user": invite.user,
                "name": invite.user.first_name if invite.user else "",
                "cta_link": event.get_full_url(),
            },
            attachments=[("event.ics", ical_data, "text/calendar")],
        )
        invite.sent_at = timezone.now()
        invite.save(update_fields=["sent_at"])
