from __future__ import annotations

from .base import *

DEBUG = bool(os.getenv("DEBUG"))

# Deploy instructions
# https://tonybaloney.github.io/posts/django-on-azure-beyond-hello-world.html
# A staging environment running the P1V2 App Service Plan (or above)
# A production environment running one or more P2V2 (or above) App Service Plans

# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases


if os.getenv("ENVIRONMENT") == "production":
    print("----------------------------------")
    print("----------------------------------")
    print("PRODUCTION")
    print("----------------------------------")
    print("----------------------------------")
    ALLOWED_HOSTS = [
        "djangonaut-space.azurewebsites.net",
        "djangonaut.space",
        "staging-djangonaut-space.azurewebsites.net",
    ]
    CSRF_TRUSTED_ORIGINS = [
        "https://djangonaut.space",
        "https://djangonaut-space.azurewebsites.net",
        "https://staging-djangonaut-space.azurewebsites.net",
    ]

    DATABASES["default"]["OPTIONS"]["sslmode"] = "require"

    EMAIL_BACKEND = "anymail.backends.mailjet.EmailBackend"
    MAILJET_API_KEY = os.getenv("MAILJET_API_KEY")
    MAILJET_SECRET_KEY = os.getenv("MAILJET_SECRET_KEY")
    ANYMAIL = {
        "MAILJET_API_KEY": MAILJET_API_KEY,
        "MAILJET_SECRET_KEY": MAILJET_SECRET_KEY,
    }
    # Azure Media and Static Storage Settings
    AZURE_ACCOUNT_NAME = os.environ.get("AZURE_ACCOUNT_NAME", "djangonaut")
    AZURE_ACCOUNT_KEY = os.environ.get("AZURE_ACCOUNT_KEY", False)
    AZURE_MEDIA_CONTAINER = os.environ.get("AZURE_MEDIA_CONTAINER", "media")
    AZURE_STATIC_CONTAINER = os.environ.get("AZURE_STATIC_CONTAINER", "static")

    DEFAULT_FILE_STORAGE = "indymeet.settings.storages.AzureMediaStorage"
    STATICFILES_STORAGE = "indymeet.settings.storages.AzureStaticStorage"

    AZURE_CUSTOM_DOMAIN = f"{AZURE_ACCOUNT_NAME}.azureedge.net"  # CDN URL
    # AZURE_CUSTOM_DOMAIN = f"{AZURE_ACCOUNT_NAME}.blob.core.windows.net"  # Files URL

    STATIC_URL = f"https://{AZURE_CUSTOM_DOMAIN}/{AZURE_STATIC_CONTAINER}/"
    MEDIA_URL = f"https://{AZURE_CUSTOM_DOMAIN}/{AZURE_MEDIA_CONTAINER}/"

try:
    from .local import *
except ImportError:
    pass


BASE_URL = os.getenv("BASE_URL", "https://djangonaut.space")

RECAPTCHA_PUBLIC_KEY = os.getenv("RECAPTCHA_PUBLIC_KEY")
RECAPTCHA_PRIVATE_KEY = os.getenv("RECAPTCHA_PRIVATE_KEY")
