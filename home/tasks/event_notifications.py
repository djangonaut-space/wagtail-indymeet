"""Background tasks for sending event-related notification emails."""

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django_tasks import task

from home import email
from home.icalendar_utils import generate_icalendar
from home.models import Event, EventCalendarInvite

# Our mail provider caps how many emails we can send per day, so invites are
# grouped into BCC emails rather than sent one per person.
CALENDAR_INVITE_BATCH_SIZE = 40


def _record_pending_invites(event: Event) -> None:
    """Record an invite for every recipient of the event not yet emailed."""
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
    """Fan out an event's calendar invites in batches of BCC recipients.

    Each batch is mailed by its own task, so a failure or retry only affects
    the recipients in that batch. Every invite not yet emailed is
    (re)scheduled, which picks up both people who joined the session since the
    last send and invites whose send never ran.

    Args:
        event_id: The ID of the Event to send invites for.
    """
    with transaction.atomic():
        event = Event.objects.filter(pk=event_id).first()
        if event is None:
            return

        _record_pending_invites(event)
        queue_calendar_invite_batches(
            list(
                event.calendar_invites.unsent()
                .order_by("pk")
                .values_list("id", flat=True)
            )
        )


def _batches(invite_ids: list[int]) -> list[list[int]]:
    return [
        invite_ids[start : start + CALENDAR_INVITE_BATCH_SIZE]
        for start in range(0, len(invite_ids), CALENDAR_INVITE_BATCH_SIZE)
    ]


def queue_calendar_invite_batches(invite_ids: list[int]) -> None:
    """Queue a send task for each batch of invites.

    Args:
        invite_ids: IDs of unsent invites, all for the same event.
    """
    for batch in _batches(invite_ids):
        send_calendar_invite_batch.enqueue(invite_ids=batch)


def _email_invite(event: Event, addresses: list[str], email_template: str) -> None:
    """Email the event's .ics to the addresses in one BCC'd message.

    Mailjet requires a To address, so the email is addressed to the sessions
    inbox.
    """
    to_address = settings.SESSIONS_FROM_EMAIL
    email.send(
        from_email=settings.SESSIONS_FROM_EMAIL,
        email_template=email_template,
        recipient_list=[to_address],
        bcc_list=[
            address for address in addresses if address.lower() != to_address.lower()
        ],
        context={
            "event": event,
            "cta_link": event.get_full_url(),
        },
        attachments=[("event.ics", generate_icalendar(event), "text/calendar")],
    )


@task()
def send_event_calendar_update(event_id: int) -> None:
    """Email the updated invite to everyone already sent one for the event.

    The sequence goes up first, so the new .ics shares the original's UID with
    a higher SEQUENCE and calendars move the existing entry rather than adding
    a second one. Invites not sent yet are skipped; their send reads the event
    when it runs, so it already has the new details.

    Args:
        event_id: The ID of the Event that changed.
    """
    with transaction.atomic():
        Event.objects.filter(pk=event_id).update(
            calendar_sequence=F("calendar_sequence") + 1
        )
        invite_ids = list(
            EventCalendarInvite.objects.filter(event_id=event_id)
            .sent()
            .order_by("pk")
            .values_list("id", flat=True)
        )
        for batch in _batches(invite_ids):
            send_calendar_update_batch.enqueue(invite_ids=batch)


@task()
def send_calendar_update_batch(invite_ids: list[int]) -> None:
    """Email a batch of recipients the updated calendar invite.

    Args:
        invite_ids: The IDs of the EventCalendarInvites to send the update to.
            They must all belong to the same event.
    """
    invites = list(
        EventCalendarInvite.objects.select_related("event").filter(pk__in=invite_ids)
    )
    if not invites:
        return
    _email_invite(
        invites[0].event,
        [invite.email for invite in invites],
        "event_calendar_update",
    )


@task()
def send_calendar_invite_batch(invite_ids: list[int]) -> None:
    """Email a batch of recipients their calendar invite and record the delivery.

    Recipients are BCC'd so they don't see each other's addresses.

    Idempotent per recipient: the invites are locked and re-checked as unsent,
    so neither a repeated fan-out nor a concurrent worker can email the same
    person twice.

    Args:
        invite_ids: The IDs of the EventCalendarInvites to send. They must all
            belong to the same event.
    """
    with transaction.atomic():
        invites = list(
            EventCalendarInvite.objects.unsent()
            # Only the invite rows: user is nullable, and Postgres can't lock
            # across the nullable side of the resulting outer join.
            .select_for_update(of=("self",))
            .select_related("event")
            .filter(pk__in=invite_ids)
        )
        if not invites:
            return

        _email_invite(
            invites[0].event,
            [invite.email for invite in invites],
            "event_calendar_invite",
        )
        EventCalendarInvite.objects.filter(
            pk__in=[invite.pk for invite in invites]
        ).update(sent_at=timezone.now())
