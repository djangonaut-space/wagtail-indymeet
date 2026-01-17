from .production import *

# Use MD5 hasher as it's much faster per:
# https://docs.djangoproject.com/en/5.0/topics/testing/overview/#password-hashing
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Use ImmediateBackend for tasks in tests so they run synchronously
TASKS = {
    "default": {
        "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
    }
}
# Disable ssl for testing on CI
DATABASES["default"].setdefault("OPTIONS", {}).pop("sslmode", None)

# The manifest storage from production.py would require collectstatic to be run
# before the tests could run.
STORAGES["staticfiles"][
    "BACKEND"
] = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Use locmem backend for email in tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Set ENVIRONMENT to production so email sending is not restricted in tests
ENVIRONMENT = "production"
