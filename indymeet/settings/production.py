from .base import *

DEBUG = os.getenv('DEBUG')

# Deploy instructions
# https://tonybaloney.github.io/posts/django-on-azure-beyond-hello-world.html
# A staging environment running the P1V2 App Service Plan (or above)
# A production environment running one or more P2V2 (or above) App Service Plans

# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases

if os.getenv('ENVIRONMENT') == 'production':
    print('----------------------------------')
    print('----------------------------------')
    print('PRODUCTION')
    print('----------------------------------')
    print('----------------------------------')
    SECRET_KEY = os.environ['SECRET_KEY']
    ALLOWED_HOSTS = ['localhost', 'https://djangonaut-space.azurewebsites.net',  'djangonaut-space.azurewebsites.net', 'https://djangonaut.space', 'djangonaut.space']

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql_psycopg2',  # 'postgresql_psycopg2', 'mysql', 'sqlite3' or 'oracle'.
            'NAME': 'djangonaut-space',                      # Or path to database file if using sqlite3.
            'USER': os.environ['USER'],                      # Not used with sqlite3.
            'PASSWORD': os.environ['PASSWORD'],                  # Not used with sqlite3.
            'HOST': os.environ['HOST'],                      # Set to empty string for localhost. Not used with sqlite3.
            'PORT': 5432,                      # Set to empty string for default. Not used with sqlite3.
            'OPTIONS': {
                'sslmode': 'require'
            },
        },
    }

    EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
    ANYMAIL = {
        "SENDGRID_API_KEY": SENDGRID_API_KEY,
    }

try:
    from .local import *
except ImportError:
    pass


RECAPTCHA_PUBLIC_KEY = os.getenv('RECAPTCHA_PUBLIC_KEY')
RECAPTCHA_PRIVATE_KEY = os.getenv('RECAPTCHA_PRIVATE_KEY')