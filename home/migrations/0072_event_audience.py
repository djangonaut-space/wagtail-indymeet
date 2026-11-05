from django.db import migrations, models


def is_public_to_audience(apps, schema_editor):
    """Public events become community events; private ones become session events."""
    Event = apps.get_model("home", "Event")
    Event.objects.filter(is_public=True).update(audience="community")
    Event.objects.filter(is_public=False).update(audience="session")


def audience_to_is_public(apps, schema_editor):
    Event = apps.get_model("home", "Event")
    Event.objects.exclude(audience="session").update(is_public=True)
    Event.objects.filter(audience="session").update(is_public=False)


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0071_eventcalendarinvite"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="audience",
            field=models.CharField(
                choices=[
                    ("public", "Public"),
                    ("session", "Session"),
                    ("community", "Community"),
                ],
                default="session",
                help_text=(
                    "Public: open to the world (e.g. a YouTube stream); visible to "
                    "everyone, and only Extra emails get a calendar invite. "
                    "Session: only for the linked session's members, who are the "
                    "only ones who can see it and get an invite (e.g. opening and "
                    "closing ceremonies). "
                    "Community: visible to everyone, and everyone who has ever been "
                    "an accepted session member gets an invite (e.g. guest "
                    "speakers). A session can be linked for context."
                ),
                max_length=16,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(is_public_to_audience, audience_to_is_public),
        migrations.RemoveField(
            model_name="event",
            name="is_public",
        ),
        migrations.AlterField(
            model_name="event",
            name="is_published",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Check this to make the event go live on the calendar and "
                    "detail pages for its audience. Unpublished events are only "
                    "visible to staff."
                ),
            ),
        ),
    ]
