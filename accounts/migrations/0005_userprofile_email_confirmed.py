# Generated by Django 4.1.5 on 2023-01-09 00:58

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_alter_userprofile_member_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="email_confirmed",
            field=models.BooleanField(default=False),
        ),
    ]
