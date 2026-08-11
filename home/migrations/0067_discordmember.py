from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0066_alter_event_is_public"),
    ]

    operations = [
        migrations.CreateModel(
            name="DiscordMember",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("discord_id", models.CharField(max_length=32, unique=True)),
                ("username", models.CharField(max_length=32)),
                (
                    "global_name",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                ("nickname", models.CharField(blank=True, default="", max_length=64)),
                ("role_ids", models.JSONField(blank=True, default=list)),
                ("is_bot", models.BooleanField(default=False)),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="False when the member left the server; kept so "
                        "profile links survive leave/rejoin.",
                    ),
                ),
                (
                    "last_seen_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
            ],
            options={
                "ordering": ["username"],
            },
        ),
    ]
