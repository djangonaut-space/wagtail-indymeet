import os

import dj_database_url
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from django.forms.renderers import TemplatesSetting
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

DEBUG = bool(os.getenv("DEBUG"))

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    (
        "django-insecure-b$)hky-=v&f&48g-dtnehezmj$w4%e+in*oe*!r=kh4n4+k0sg"
        if DEBUG
        else ""
    ),
)
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set.")

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
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

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "accounts",
    "home",
    "anymail",
    "django_recaptcha",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.table_block",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "home.apps.CustomImagesAppConfig",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    # puput support
    "wagtail.contrib.legacy.richtext",
    "wagtail.contrib.search_promotions",
    "wagtail.contrib.sitemaps",
    "wagtail.contrib.routable_page",
    "puput",
    "modelcluster",
    "taggit",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.forms",
    # other
    "django_extensions",
    "django_filters",
    "django_tasks",
    "django_tasks_db",
    "storages",
    "tailwind",
    "theme",
    "widget_tweaks",
    "import_export",
    "django.contrib.gis",
    "rest_framework",
    "rest_framework_gis",
    "wagtailgeowidget",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

INTERNAL_IPS = ["127.0.0.1"]

ROOT_URLCONF = "indymeet.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(PROJECT_DIR, "templates"),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "home.context_processors.alert_about_status",
                "home.context_processors.nav_session_links",
            ],
        },
    },
]

WSGI_APPLICATION = "indymeet.wsgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    "default": dj_database_url.config(
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# _db_ssl = os.getenv("DATABASE_SSL", "false" if DEBUG else "true").lower() == "true"
# if _db_ssl:
#    DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = "require"

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

# ---------------------------------------------------------------------------
# Static / Media files
# ---------------------------------------------------------------------------

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

STATICFILES_DIRS = [
    os.path.join(PROJECT_DIR, "static"),
    os.path.join(BASE_DIR, "theme", "static"),
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": os.getenv(
            "STATICFILES_BACKEND",
            "django.contrib.staticfiles.storage.StaticFilesStorage",
        ),
    },
}

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATIC_URL = "/static/"

MEDIA_ROOT = os.path.join(BASE_DIR, "mediafiles")
MEDIA_URL = "/media/"

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

TASKS = {
    "default": {
        "BACKEND": os.getenv(
            "TASK_BACKEND",
            # Run tasks synchronously in development so tests and manual testing
            # see results immediately without a separate worker process.
            "django_tasks.backends.immediate.ImmediateBackend",
        ),
    }
}

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    # Use locmem in development so pytest's mail.outbox works and emails
    # don't require a mail server. Override with EMAIL_BACKEND=console in
    # .env.docker if you want emails printed to the Docker logs instead.
    "django.core.mail.backends.locmem.EmailBackend",
)

if EMAIL_BACKEND == "anymail.backends.mailjet.EmailBackend":
    MAILJET_API_KEY = os.getenv("MAILJET_API_KEY")
    MAILJET_SECRET_KEY = os.getenv("MAILJET_SECRET_KEY")
    ANYMAIL = {
        "MAILJET_API_KEY": MAILJET_API_KEY,
        "MAILJET_SECRET_KEY": MAILJET_SECRET_KEY,
    }

# ---------------------------------------------------------------------------
# reCAPTCHA
# ---------------------------------------------------------------------------

RECAPTCHA_PUBLIC_KEY = os.getenv(
    "RECAPTCHA_PUBLIC_KEY",
    "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI" if DEBUG else None,
)
RECAPTCHA_PRIVATE_KEY = os.getenv(
    "RECAPTCHA_PRIVATE_KEY",
    "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe" if DEBUG else None,
)

SILENCED_SYSTEM_CHECKS = ["django_recaptcha.recaptcha_test_key_error"]

# ---------------------------------------------------------------------------
# Wagtail
# ---------------------------------------------------------------------------

WAGTAIL_SITE_NAME = "indymeet"

WAGTAILSEARCH_BACKENDS = {
    "default": {
        "BACKEND": "wagtail.search.backends.database",
    }
}

WAGTAILADMIN_BASE_URL = "https://djangonaut.space"

AUTH_USER_MODEL = "accounts.CustomUser"

LOGOUT_REDIRECT_URL = "/"

DEFAULT_FROM_EMAIL = "contact@djangonaut.space"
SERVER_EMAIL = "contact@djangonaut.space"

PUPUT_AS_PLUGIN = True
PUPUT_BLOG_MODEL = "home.models.puput_abstracts.BlogAbstract"
PUPUT_ENTRY_MODEL = "home.models.puput_abstracts.EntryAbstract"

MIGRATION_MODULES = {"puput": "home.puput_migrations"}

TAILWIND_APP_NAME = "theme"

# ---------------------------------------------------------------------------
# Sentry (production only)
# ---------------------------------------------------------------------------

_sentry_dsn = os.environ.get("SENTRY_DNS")
if not DEBUG and _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=0.25,
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


# ---------------------------------------------------------------------------
# Django Debug Toolbar (optional)
# ---------------------------------------------------------------------------

if os.environ.get("ENABLE_TOOLBAR"):
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "root": {"level": "WARNING", "handlers": ["console"]},
    "formatters": {"simple": {"format": "%(levelname)s %(message)s"}},
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "django.request": {"handlers": [], "level": "ERROR"},
    },
}

# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


class FormRenderer(TemplatesSetting):
    form_template_name = "forms/form.html"


FORM_RENDERER = "indymeet.settings.FormRenderer"

# Should be removed in Django 6.0
FORMS_URLFIELD_ASSUME_HTTPS = True

# ---------------------------------------------------------------------------
# Application settings
# ---------------------------------------------------------------------------

# Identify what environment the application is running in.
# The value for production is "production". Email subjects are prefixed with
# the environment name when ENVIRONMENT != "production".
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")

BASE_URL = os.getenv(
    "BASE_URL",
    "http://localhost:8000",
)

# Any emails specified here can receive transactional emails in non-production environments.
ALLOWED_EMAILS_FOR_TESTING = [
    email
    for email in (os.environ.get("ALLOWED_EMAILS_FOR_TESTING") or "").split(";")
    if email
]

# When running load tests, it's helpful to remove some functionality
# such as confirmation emails.
LOAD_TESTING = os.environ.get("LOAD_TESTING", False)
