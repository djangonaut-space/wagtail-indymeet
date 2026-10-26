import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q

from home import constants


def backfill_sent_invites(apps, schema_editor):
    """Record an invite for every recipient of an already-sent event.

    Events used to track a single send time for the whole event, with no
    account of who it reached. Without this, the send action would see those
    events as having nobody invited yet and mail their whole recipient list a
    second time. The recipient list is recomputed from current membership,
    which is the closest we can get to who the original send reached.
    """
    Event = apps.get_model("home", "Event")
    SessionMembership = apps.get_model("home", "SessionMembership")
    EventCalendarInvite = apps.get_model("home", "EventCalendarInvite")
    User = apps.get_model(settings.AUTH_USER_MODEL)

    accepted = SessionMembership.objects.filter(
        Q(role=constants.DJANGONAUT, accepted=True)
        | Q(
            role__in=[constants.CAPTAIN, constants.NAVIGATOR, constants.ORGANIZER],
        )
    )
    users_by_email = {
        email.lower(): pk
        for pk, email in User.objects.exclude(email="").values_list("pk", "email")
    }

    invites = []
    for event in Event.objects.filter(calendar_invites_sent_at__isnull=False):
        recipients = {
            address.lower() for address in (event.extra_emails or []) if address
        }
        if event.session_id:
            memberships = accepted.filter(session_id=event.session_id)
        elif event.is_public:
            memberships = accepted
        else:
            memberships = SessionMembership.objects.none()
        recipients.update(
            address.lower()
            for address in memberships.exclude(user__email="").values_list(
                "user__email", flat=True
            )
        )
        invites.extend(
            EventCalendarInvite(
                event_id=event.pk,
                email=address,
                user_id=users_by_email.get(address),
                sent_at=event.calendar_invites_sent_at,
            )
            for address in sorted(recipients)
        )
    EventCalendarInvite.objects.bulk_create(invites, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0070_remove_tutorialevaluation_next_evaluation_at_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EventCalendarInvite",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("email", models.EmailField(max_length=254)),
                (
                    "sent_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="The date and time this invite was successfully sent.",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calendar_invites",
                        to="home.event",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="event_calendar_invites",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("email",),
            },
        ),
        migrations.AddField(
            model_name="event",
            name="calendar_invite_recipients",
            field=models.ManyToManyField(
                blank=True,
                help_text="Users who have been given a calendar invite for this event.",
                related_name="calendar_invite_events",
                through="home.EventCalendarInvite",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="eventcalendarinvite",
            constraint=models.UniqueConstraint(
                models.F("event"),
                django.db.models.functions.text.Lower("email"),
                name="home_eventcalendarinvite_event_email_unq",
            ),
        ),
        migrations.RunPython(
            backfill_sent_invites, migrations.RunPython.noop, elidable=True
        ),
        migrations.RemoveField(
            model_name="event",
            name="calendar_invites_sent_at",
        ),
    ]
