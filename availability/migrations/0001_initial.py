"""Move ``UserAvailability`` from the ``accounts`` app into ``availability``.

The model previously lived in ``accounts`` (table ``accounts_useravailability``).
This migration moves it without dropping the data:

- The Django *state* gains ``availability.UserAvailability`` (via
  ``SeparateDatabaseAndState``) while the paired ``accounts`` migration removes
  it from state only.
- The physical table is renamed to match the new app label with a reversible
  ``RunSQL`` (a metadata-only rename on PostgreSQL).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0009_useravailability"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="UserAvailability",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("slots", models.JSONField(blank=True, default=list)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "user",
                            models.OneToOneField(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="availability",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "User Availability",
                        "verbose_name_plural": "User Availabilities",
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE accounts_useravailability "
                        "RENAME TO availability_useravailability;"
                    ),
                    reverse_sql=(
                        "ALTER TABLE availability_useravailability "
                        "RENAME TO accounts_useravailability;"
                    ),
                ),
            ],
        ),
    ]
