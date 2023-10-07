# Generated by Django 4.1.12 on 2023-10-07 12:34

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0014_session_slug_alter_event_slug"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="slug",
            field=models.SlugField(
                help_text="This is used in the URL to identify the event."
            ),
        ),
        migrations.AlterField(
            model_name="session",
            name="slug",
            field=models.SlugField(
                help_text="This is used in the URL to identify the session.",
                unique=True,
            ),
        ),
    ]