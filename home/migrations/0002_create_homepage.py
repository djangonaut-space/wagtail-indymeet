from django.db import migrations


class Migration(migrations.Migration):
    """Previously created the HomePage and default Site.

    home.receivers.ensure_site_structure does that now, after every
    migrate and flush, so the rows also come back after tests flush the
    database.
    """

    run_before = [
        ("wagtailcore", "0053_locale_model"),
    ]

    dependencies = [
        ("home", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            migrations.RunPython.noop, migrations.RunPython.noop, elidable=True
        ),
    ]
