from __future__ import annotations

from .production import *

#    Get rid of whitenoise "No directory at" warning, as it's not helpful when running tests.
# Related:
# - https://github.com/evansd/whitenoise/issues/215
# - https://github.com/evansd/whitenoise/issues/191
# - https://github.com/evansd/whitenoise/commit/4204494d44213f7a51229de8bc224cf6d84c01eb
WHITENOISE_AUTOREFRESH = True

# Use MD5 hasher as it's much faster per:
# https://docs.djangoproject.com/en/5.0/topics/testing/overview/#password-hashing
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
