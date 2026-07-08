from io import StringIO
from unittest import mock

from django.core import management
from django.core.management import CommandError
from django.db import DatabaseError
from django.test import SimpleTestCase

from home.management.commands.build_test_db_template import Command


class FakeCreation:
    def __init__(self):
        self.create_test_db = mock.Mock()


class FakeConnection:
    def __init__(self, settings_dict):
        self.settings_dict = settings_dict
        self.creation = FakeCreation()
        self.close = mock.Mock()


class BuildTestDbTemplateCommandTests(SimpleTestCase):
    def _settings_dict(self, template="template_wagtail_indymeet_test"):
        return {
            "NAME": "djangonaut-space",
            "TEST": {"TEMPLATE": template} if template else {},
        }

    def test_raises_when_template_not_configured(self):
        connection = FakeConnection(self._settings_dict(template=None))

        with mock.patch(
            "home.management.commands.build_test_db_template.connections",
            {"default": connection},
        ):
            with self.assertRaisesMessage(
                CommandError,
                "DATABASES['default']['TEST']['TEMPLATE'] is not configured.",
            ):
                management.call_command("build_test_db_template", stdout=StringIO())

        connection.creation.create_test_db.assert_not_called()

    def test_skips_rebuild_when_already_up_to_date(self):
        connection = FakeConnection(self._settings_dict())

        out = StringIO()
        with (
            mock.patch(
                "home.management.commands.build_test_db_template.connections",
                {"default": connection},
            ),
            mock.patch.object(
                Command, "_is_up_to_date", return_value=True
            ) as is_up_to_date,
        ):
            management.call_command("build_test_db_template", stdout=out)

        is_up_to_date.assert_called_once_with(
            connection, "template_wagtail_indymeet_test"
        )
        connection.creation.create_test_db.assert_not_called()
        self.assertIn("already reflects every migration", out.getvalue())

    def test_force_rebuilds_without_checking_up_to_date(self):
        connection = FakeConnection(self._settings_dict())

        with (
            mock.patch(
                "home.management.commands.build_test_db_template.connections",
                {"default": connection},
            ),
            mock.patch.object(Command, "_is_up_to_date") as is_up_to_date,
        ):
            management.call_command(
                "build_test_db_template", "--force", stdout=StringIO()
            )

        is_up_to_date.assert_not_called()
        connection.creation.create_test_db.assert_called_once()

    def test_builds_template_as_plain_database_and_restores_settings(self):
        settings_dict = self._settings_dict()
        connection = FakeConnection(settings_dict)
        captured_test_settings_during_build = {}

        def capture_settings(*args, **kwargs):
            captured_test_settings_during_build.update(settings_dict["TEST"])

        connection.creation.create_test_db.side_effect = capture_settings

        out = StringIO()
        with (
            mock.patch(
                "home.management.commands.build_test_db_template.connections",
                {"default": connection},
            ),
            mock.patch.object(Command, "_is_up_to_date", return_value=False),
        ):
            management.call_command("build_test_db_template", stdout=out)

        connection.creation.create_test_db.assert_called_once_with(
            verbosity=1, autoclobber=True, serialize=False, keepdb=False
        )
        # While building, the template is a plain database (no TEMPLATE key)
        # named after the template, not cloned from itself.
        self.assertNotIn("TEMPLATE", captured_test_settings_during_build)
        self.assertEqual(
            captured_test_settings_during_build["NAME"],
            "template_wagtail_indymeet_test",
        )

        # Settings are restored afterwards.
        self.assertEqual(
            settings_dict["TEST"]["TEMPLATE"], "template_wagtail_indymeet_test"
        )
        self.assertIsNone(settings_dict["TEST"]["NAME"])
        self.assertEqual(settings_dict["NAME"], "djangonaut-space")
        connection.close.assert_called_once()

        self.assertIn(
            'Built test database template "template_wagtail_indymeet_test".',
            out.getvalue(),
        )

    def test_restores_settings_even_when_create_test_db_fails(self):
        settings_dict = self._settings_dict()
        connection = FakeConnection(settings_dict)
        connection.creation.create_test_db.side_effect = Exception("boom")

        with (
            mock.patch(
                "home.management.commands.build_test_db_template.connections",
                {"default": connection},
            ),
            mock.patch.object(Command, "_is_up_to_date", return_value=False),
        ):
            with self.assertRaisesMessage(Exception, "boom"):
                management.call_command("build_test_db_template", stdout=StringIO())

        self.assertEqual(
            settings_dict["TEST"]["TEMPLATE"], "template_wagtail_indymeet_test"
        )
        self.assertEqual(settings_dict["NAME"], "djangonaut-space")


class IsUpToDateTests(SimpleTestCase):
    def _connection(self):
        return FakeConnection(
            {
                "NAME": "djangonaut-space",
                "TEST": {"TEMPLATE": "template_wagtail_indymeet_test"},
            }
        )

    def test_returns_false_and_restores_name_when_database_is_unreachable(self):
        connection = self._connection()

        with mock.patch(
            "home.management.commands.build_test_db_template.MigrationExecutor",
            side_effect=DatabaseError("database does not exist"),
        ):
            result = Command()._is_up_to_date(
                connection, "template_wagtail_indymeet_test"
            )

        self.assertFalse(result)
        self.assertEqual(connection.settings_dict["NAME"], "djangonaut-space")
        connection.close.assert_called()

    def test_returns_true_when_no_migrations_are_pending(self):
        connection = self._connection()
        executor = mock.Mock()
        executor.migration_plan.return_value = []

        with mock.patch(
            "home.management.commands.build_test_db_template.MigrationExecutor",
            return_value=executor,
        ):
            result = Command()._is_up_to_date(
                connection, "template_wagtail_indymeet_test"
            )

        self.assertTrue(result)
        self.assertEqual(connection.settings_dict["NAME"], "djangonaut-space")

    def test_returns_false_when_migrations_are_pending(self):
        connection = self._connection()
        executor = mock.Mock()
        executor.migration_plan.return_value = [("home", "0002_something")]

        with mock.patch(
            "home.management.commands.build_test_db_template.MigrationExecutor",
            return_value=executor,
        ):
            result = Command()._is_up_to_date(
                connection, "template_wagtail_indymeet_test"
            )

        self.assertFalse(result)
