from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0050_add_djangonauts_have_access_to_session"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="is_public",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="event",
            name="extra_emails",
            field=models.JSONField(
                blank=True,
                default=["sessions@djangonaut.space"],
                help_text="Comma-separated email addresses to include in calendar invites (e.g. guest speakers). Defaults to sessions@djangonaut.space.",
            ),
        ),
    ]
