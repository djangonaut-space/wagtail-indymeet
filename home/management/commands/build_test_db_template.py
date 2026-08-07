"""
Build (or refresh) the migrated template database referenced by
``DATABASES[...]["TEST"]["TEMPLATE"]`` (see ``indymeet/settings.py``).

Postgres can copy an already-migrated database far faster than Django can
replay every Wagtail + application migration, which matters most for
pytest-xdist, where each worker builds its own test database from scratch.

Application migrations change often enough that a stale template is a real
risk, so this command checks whether the template already reflects every
migration before doing the expensive rebuild. That makes it safe to run
before every Playwright test run instead of relying on remembering to re-run
it after pulling migrations.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connections
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = (
        "Build/refresh the migrated template database referenced by "
        "DATABASES[...]['TEST']['TEMPLATE'], used to seed the test database for "
        "the Playwright suite instead of replaying every migration. Skips the "
        "rebuild when the template already reflects every migration, so it's "
        "safe to run before every Playwright test run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            dest="alias",
            help="Alias of the database whose TEST TEMPLATE should be (re)built.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild the template even if it already reflects every migration.",
        )

    def handle(self, *args, alias, force, **options):
        connection = connections[alias]
        test_settings = connection.settings_dict.setdefault("TEST", {})

        match test_settings.get("TEMPLATE"):
            case None | "":
                raise CommandError(
                    f"DATABASES['{alias}']['TEST']['TEMPLATE'] is not configured."
                )
            case template_name:
                original_name = connection.settings_dict["NAME"]
                original_test_name = test_settings.get("NAME")

        if not force and self._is_up_to_date(connection, template_name):
            self.stdout.write(
                f'Test database template "{template_name}" already reflects '
                "every migration; skipping rebuild."
            )
            return

        # Build the template as a plain database rather than cloning it from
        # itself.
        del test_settings["TEMPLATE"]
        test_settings["NAME"] = template_name

        try:
            connection.creation.create_test_db(
                verbosity=options["verbosity"],
                autoclobber=True,
                keepdb=False,
            )
        finally:
            connection.close()
            test_settings["TEMPLATE"] = template_name
            test_settings["NAME"] = original_test_name
            connection.settings_dict["NAME"] = original_name

        self.stdout.write(
            self.style.SUCCESS(f'Built test database template "{template_name}".')
        )

    def _is_up_to_date(self, connection, template_name):
        """Whether template_name already has every migration applied."""
        original_name = connection.settings_dict["NAME"]
        connection.settings_dict["NAME"] = template_name
        connection.close()
        try:
            executor = MigrationExecutor(connection)
        except DatabaseError:
            # The template database doesn't exist yet (or can't be reached);
            # treat that as stale so it gets built.
            return False
        else:
            return not executor.migration_plan(executor.loader.graph.leaf_nodes())
        finally:
            connection.close()
            connection.settings_dict["NAME"] = original_name
