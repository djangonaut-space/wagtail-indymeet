import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0020_userprofile_timezone"),
        ("home", "0067_discordmember"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="discord_username",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Legacy Discord username used only to backfill "
                "discord_member links. Prefer discord_member.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="discord_member",
            field=models.OneToOneField(
                blank=True,
                help_text="Linked Discord guild member used to grant channel access "
                "during sessions.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="profile",
                to="home.discordmember",
            ),
        ),
    ]
