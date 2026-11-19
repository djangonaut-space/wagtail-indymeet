import tempfile
from pathlib import Path

import time_machine
from django.core.mail import EmailMessage, get_connection
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.factories import UserFactory
from home import email

BACKEND = "home.email_backends.SubjectFileEmailBackend"


class SubjectFileEmailBackendTests(SimpleTestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "emails"

    @time_machine.travel("2026-10-23 14:05:09.123456", tick=False)
    def test_writes_one_file_per_message_named_by_date_time_subject(self) -> None:
        connection = get_connection(BACKEND, file_path=str(self.dir))
        sent = connection.send_messages(
            [
                EmailMessage("Hello World!", "Body one", to=["a@example.com"]),
                EmailMessage("[dev] Second", "Body two", to=["b@example.com"]),
            ]
        )

        self.assertEqual(sent, 2)
        files = sorted(p.name for p in self.dir.iterdir())
        self.assertEqual(
            files,
            [
                "email_2026-10-23_14-05-09-123456_dev-second.txt",
                "email_2026-10-23_14-05-09-123456_hello-world.txt",
            ],
        )
        content = (self.dir / files[1]).read_text()
        self.assertIn("Subject: Hello World!", content)
        self.assertIn("To: a@example.com", content)
        self.assertIn("Body one", content)

    def test_skips_messages_without_recipients(self) -> None:
        connection = get_connection(BACKEND, file_path=str(self.dir))
        sent = connection.send_messages([EmailMessage("No one", "Body")])

        self.assertEqual(sent, 0)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_uses_email_file_path_setting(self) -> None:
        with override_settings(EMAIL_FILE_PATH=str(self.dir)):
            get_connection(BACKEND).send_messages(
                [EmailMessage("", "Body", to=["a@example.com"])]
            )

        [path] = self.dir.iterdir()
        self.assertTrue(path.name.endswith("_no-subject.txt"))


class SendWithFileBackendTests(TestCase):
    @override_settings(
        ENVIRONMENT="dev",
        EMAIL_BACKEND=BACKEND,
        ALLOWED_EMAILS_FOR_TESTING=[],
    )
    def test_send_does_not_filter_recipients_for_file_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(EMAIL_FILE_PATH=tmp):
                email.send(
                    email_template="application_created",
                    recipient_list=["notallowed@example.com"],
                    context={"user": UserFactory.create()},
                )
            [path] = Path(tmp).iterdir()

        self.assertIn("djangonaut-space-application-submitted", path.name)
