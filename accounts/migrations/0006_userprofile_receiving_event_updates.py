# Generated by Django 4.1.5 on 2023-01-20 18:14

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_userprofile_email_confirmed"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="receiving_event_updates",
            field=models.BooleanField(default=False),
        ),
    ]
