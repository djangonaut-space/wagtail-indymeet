import os

import dj_database_url
import sentry_sdk
from django.forms.renderers import TemplatesSetting
from dotenv import load_dotenv
from sentry_sdk.integrations.django import DjangoIntegration

load_dotenv()

DEBUG = bool(os.getenv("DEBUG"))

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)

SECRET_KEY = os.environ.get("SECRET_KEY")
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

INSTALLED_APPS = [
    "accounts",
    "home.apps.HomeAppConfig",
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
    "django.contrib.postgres",
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

DATABASES = {
    "default": dj_database_url.config(
        conn_max_age=600,
        conn_health_checks=True,
        engine="django.contrib.gis.db.backends.postgis",
    )
}

# When TEST_DB_TEMPLATE is set, Postgres clones that already-migrated database
# when pytest-django/pytest-xdist build a test database, instead of replaying
# every migration. Unset (the default) leaves test database creation
# unaffected. Used for the Playwright suite via `just test-playwright`; see
# `just build-test-db-template`.
DATABASES["default"]["TEST"] = {
    "TEMPLATE": os.getenv("TEST_DB_TEMPLATE", ""),
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}

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

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

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

RECAPTCHA_PUBLIC_KEY = os.getenv(
    "RECAPTCHA_PUBLIC_KEY",
    "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI" if DEBUG else None,
)
RECAPTCHA_PRIVATE_KEY = os.getenv(
    "RECAPTCHA_PRIVATE_KEY",
    "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe" if DEBUG else None,
)

SILENCED_SYSTEM_CHECKS = ["django_recaptcha.recaptcha_test_key_error"]

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


if os.environ.get("ENABLE_TOOLBAR"):
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]

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
        "home.services.github_stats": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


class FormRenderer(TemplatesSetting):
    form_template_name = "forms/form.html"


FORM_RENDERER = "indymeet.settings.FormRenderer"

# Transitional setting: opts into Django 7.0's default of urlize/urlizetrunc
# linking bare domains as https:// instead of http://.
URLIZE_ASSUME_HTTPS = True

# Cloudflare settings
CLOUDFLARE_BEARER_TOKEN = os.getenv("CLOUDFLARE_BEARER_TOKEN")
CLOUDFLARE_ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
if CLOUDFLARE_BEARER_TOKEN and CLOUDFLARE_ZONE_ID:
    WAGTAILFRONTENDCACHE = {
        "cloudflare": {
            "BACKEND": "wagtail.contrib.frontend_cache.backends.CloudflareBackend",
            "BEARER_TOKEN": CLOUDFLARE_BEARER_TOKEN,
            "ZONEID": CLOUDFLARE_ZONE_ID,
        },
    }

# Application settings

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

# Zoom Server-to-Server OAuth credentials for automatic meeting creation.
# Set all three to enable; leave unset to disable the feature.
ZOOM_ACCOUNT_ID = os.environ.get("ZOOM_ACCOUNT_ID")
ZOOM_CLIENT_ID = os.environ.get("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.environ.get("ZOOM_CLIENT_SECRET")

# Buttondown newsletter integration.
# Set to enable; leave unset to disable.
BUTTONDOWN_API_KEY = os.environ.get("BUTTONDOWN_API_KEY")
BUTTONDOWN_WEBHOOK_SECRET = os.environ.get("BUTTONDOWN_WEBHOOK_SECRET")

# Discord scheduled-event sync and session channel/role management.
# Set DISCORD_BOT_TOKEN and DISCORD_GUILD_ID to enable; leave unset to disable.
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID")

# Id of the bot's own role on the guild (Discord assigns this automatically
# when the bot is invited with the `bot` OAuth2 scope). Session setup/teardown
# grant this role explicit view access on every private channel they manage,
# since Discord only bypasses per-channel overwrites for Administrator — see
# docs/integrations/discord.md.
DISCORD_BOT_ROLE_ID = os.environ.get("DISCORD_BOT_ROLE_ID")

# GitHub API token for Djangonaut stats collection (Issue #615).
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# When running load tests, it's helpful to remove some functionality
# such as confirmation emails.
LOAD_TESTING = os.environ.get("LOAD_TESTING", False)
