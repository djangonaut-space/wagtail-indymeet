"""Field-level encryption for sensitive calendar credentials.

Tokens are encrypted at rest with Fernet (AES-128) so a raw database dump never
exposes usable credentials. The key comes from
``settings.CALENDAR_TOKEN_ENCRYPTION_KEY`` (a url-safe base64 32-byte key).
"""

from functools import lru_cache

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = getattr(settings, "CALENDAR_TOKEN_ENCRYPTION_KEY", None)
    if not key:
        raise ImproperlyConfigured(
            "CALENDAR_TOKEN_ENCRYPTION_KEY must be set to use encrypted "
            "calendar fields. Generate one with "
            "`python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'`."
        )
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


class EncryptedTextField(models.TextField):
    """A TextField whose value is transparently encrypted in the database.

    Empty values are stored as-is (unencrypted empty strings) so that blank
    rows remain queryable/nullable without needing the key.
    """

    description = "Text stored encrypted at rest"

    def get_prep_value(self, value: str | None) -> str | None:
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        return _fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection) -> str | None:
        if value in (None, ""):
            return value
        return _fernet().decrypt(value.encode()).decode()
