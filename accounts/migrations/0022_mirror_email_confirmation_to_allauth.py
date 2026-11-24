from django.db import migrations


def create_email_addresses(apps, schema_editor):
    """
    Give every existing user an allauth ``EmailAddress`` matching their profile.

    New and changed profiles are mirrored by a signal receiver; this covers the
    users who signed up before allauth was installed.
    """
    User = apps.get_model("accounts", "CustomUser")
    EmailAddress = apps.get_model("account", "EmailAddress")
    users = (
        User.objects.exclude(email="")
        .values_list("pk", "email", "profile__email_confirmed")
        .iterator()
    )
    EmailAddress.objects.bulk_create(
        (
            EmailAddress(
                user_id=pk,
                email=email.lower(),
                verified=bool(email_confirmed),
                primary=True,
            )
            for pk, email, email_confirmed in users
        ),
        batch_size=1000,
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0021_discordmember_discordrole_and_more"),
        ("account", "0009_emailaddress_unique_primary_email"),
    ]

    operations = [
        migrations.RunPython(create_email_addresses, migrations.RunPython.noop),
    ]
