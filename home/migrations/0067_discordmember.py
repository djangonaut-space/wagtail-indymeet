from django.db import migrations, models


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
                ("nickname", models.CharField(blank=True, default="", max_length=64)),
                ("role_ids", models.JSONField(blank=True, default=list)),
                (
                    "display_name",
                    models.GeneratedField(
                        db_persist=True,
                        expression=models.Case(
                            models.When(nickname="", then=models.F("username")),
                            default=models.F("nickname"),
                        ),
                        output_field=models.CharField(max_length=64),
                    ),
                ),
            ],
            options={
                "ordering": ["display_name"],
            },
        ),
    ]
