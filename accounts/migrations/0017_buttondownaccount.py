from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_userprofile_interested_in_validator"),
    ]

    operations = [
        migrations.CreateModel(
            name="ButtondownAccount",
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
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="buttondown_account",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("buttondown_identifier", models.CharField(max_length=255)),
                ("last_updated", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="buttondownaccount",
            constraint=models.UniqueConstraint(
                fields=["buttondown_identifier"],
                name="unique_buttondown_identifier",
            ),
        ),
    ]
