from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage
from django.utils.text import slugify


class SubjectFileEmailBackend(BaseEmailBackend):
    """Write each outgoing email to its own file for local development.

    Unlike Django's ``filebased.EmailBackend`` (one ``.log`` file per
    connection, named by timestamp and id), this writes one file per message
    named ``email_<YYYY-MM-DD>_<HH-MM-SS-ffffff>_<subject-slug>.txt`` so
    emails are easy to find by browsing the directory.

    Files are written to ``settings.EMAIL_FILE_PATH``, or the ``file_path``
    keyword argument when given.
    """

    def __init__(self, *args: Any, file_path: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.file_path = Path(file_path or settings.EMAIL_FILE_PATH)
        self.file_path.mkdir(parents=True, exist_ok=True)

    def send_messages(self, email_messages: list[EmailMessage]) -> int:
        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            self._message_path(message).write_bytes(message.message().as_bytes())
            sent += 1
        return sent

    def _message_path(self, message: EmailMessage) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
        subject = slugify(message.subject)[:80] or "no-subject"
        return self.file_path / f"email_{timestamp}_{subject}.txt"
