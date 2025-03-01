from .production import *

# Use MD5 hasher as it's much faster per:
# https://docs.djangoproject.com/en/5.0/topics/testing/overview/#password-hashing
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
# Disable ssl for testing on CI
DATABASES["default"].setdefault("OPTIONS", {}).pop("sslmode", None)
