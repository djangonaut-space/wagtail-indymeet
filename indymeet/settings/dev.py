# ----------------------------------------------
# For developing locally
# ----------------------------------------------
from .base import *
from dotenv import load_dotenv

load_dotenv()

###  SQLite (deprecated)
if os.getenv('ENVIRONMENT') == 'dev':
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
        }
    }

print('----------------------------------')
print('----------------------------------')
print('DEV')
print('----------------------------------')
print('----------------------------------')


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-b$)hky-=v&f&48g-dtnehezmj$w4%e+in*oe*!r=kh4n4+k0sg"

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


try:
    from .local import *
except ImportError:
    pass


RECAPTCHA_PUBLIC_KEY = os.getenv('RECAPTCHA_PUBLIC_KEY')
RECAPTCHA_PRIVATE_KEY = os.getenv('RECAPTCHA_PRIVATE_KEY')

SILENCED_SYSTEM_CHECKS = ['captcha.recaptcha_test_key_error']
