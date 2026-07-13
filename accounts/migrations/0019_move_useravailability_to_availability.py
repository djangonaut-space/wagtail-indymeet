"""Remove ``UserAvailability`` from the ``accounts`` state.

The model (and its table) now live in the ``availability`` app. The physical
table rename and the state re-creation happen in ``availability.0001_initial``;
here we only drop the model from ``accounts``' migration state so the two apps
agree on the final schema. No database operations are performed.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_userprofile_discord_username"),
        ("availability", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="UserAvailability"),
            ],
            database_operations=[],
        ),
    ]
