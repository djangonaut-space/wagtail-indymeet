import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *

DEBUG = bool(os.getenv("DEBUG"))

# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases

ALLOWED_HOSTS = [
    "djangonaut.space",
    "dev.djangonaut.space",
    "staging.djangonaut.space",
]
CSRF_TRUSTED_ORIGINS = [
    "https://djangonaut.space",
    "https://dev.djangonaut.space",
    "https://staging.djangonaut.space",
]
# dj_database_url doesn't render an OPTIONS dictionary
# unless there was a setting that needs it.
DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = "require"

EMAIL_BACKEND = "anymail.backends.mailjet.EmailBackend"
MAILJET_API_KEY = os.getenv("MAILJET_API_KEY")
MAILJET_SECRET_KEY = os.getenv("MAILJET_SECRET_KEY")
ANYMAIL = {
    "MAILJET_API_KEY": MAILJET_API_KEY,
    "MAILJET_SECRET_KEY": MAILJET_SECRET_KEY,
}

SENTRY_DNS = os.environ.get("SENTRY_DNS")
sentry_sdk.init(
    dsn=SENTRY_DNS,
    # Set traces_sample_rate to 1.0 to capture 100% of transactions for performance monitoring.
    traces_sample_rate=0.25,
    # Set profiles_sample_rate to 1.0 to profile 100% of sampled transactions.
    profiles_sample_rate=0.1,
    integrations=[
        DjangoIntegration(
            transaction_style="url",
            middleware_spans=True,
            signals_spans=False,
            cache_spans=False,
        ),
    ],
)

BASE_URL = os.getenv("BASE_URL", "https://djangonaut.space")

RECAPTCHA_PUBLIC_KEY = os.getenv("RECAPTCHA_PUBLIC_KEY")
RECAPTCHA_PRIVATE_KEY = os.getenv("RECAPTCHA_PRIVATE_KEY")
