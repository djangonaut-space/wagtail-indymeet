# Event Calendar Invites

Calendar invites for an event are sent one email per recipient, each with its
own `.ics` attachment. Every send is recorded against the recipient, so the
admin can show who has been invited and a repeat send only reaches people who
haven't been.

## Who gets an invite

Recipients are worked out when the send runs, from the event and its
`Extra emails`:

| Event | Recipients |
| --- | --- |
| Linked to a session | Accepted members of that session, plus extra emails |
| Public, no session | All accepted session members, plus extra emails |
| Private, no session | Extra emails only |

Extra emails are for people without an account here, such as guest speakers.

## Sending

1. Select the events in `/django-admin/home/event/` and run **Send calendar
   invites to event members**.
2. The confirmation page lists, per event, who would be emailed and how many
   recipients have already had their invite. Nothing is queued until you
   confirm.
3. Each recipient's email is queued separately, so a bad address or a retry
   only affects that one person.

Running the action again is safe: anyone already emailed is left alone, and an
invite whose email never went out is queued again. That makes it the right way
to catch up after new members join a session, after extra emails are added to
an event, or after a send failed.

## Resending

**Reset calendar invites sent so they can be resent** clears every recipient's
sent stamp for the selected events. The next send then mails everyone again —
use it when event details change and all recipients need the new `.ics`.

## Checking what was sent

The **Calendar invites** section at the bottom of an event's admin page lists
every recipient, the account it matched (blank for extra emails), and when
their invite went out. An invite with no sent time is still queued.

The invites are the only record of what was sent, so the event's **Calendar
invites sent** column is derived from them: it shows the most recent delivery
to any recipient, and is empty until somebody has been emailed.
