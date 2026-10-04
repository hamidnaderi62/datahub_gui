
from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


# Configure all deployment-specific values outside source control.
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError('DJANGO_SECRET_KEY must be configured')

DEBUG = env_bool('DJANGO_DEBUG', False)
ALLOWED_HOSTS = [host.strip() for host in os.environ.get(
    'DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1'
).split(',') if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get(
    'DJANGO_CSRF_TRUSTED_ORIGINS', ''
).split(',') if origin.strip()]

# Development prints verification messages to the container log. Production should
# set EMAIL_BACKEND to Django's SMTP backend and provide the SMTP variables.
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND') or (
    'django.core.mail.backends.console.EmailBackend'
    if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '10'))
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'no-reply@datahub.local')

# Pipeline workers are opt-in for local development; Compose enables dispatch.
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_TASK_DEFAULT_QUEUE = 'pipeline'
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = int(os.environ.get('CELERY_TASK_TIME_LIMIT', '1800'))
CELERY_TASK_SOFT_TIME_LIMIT = int(os.environ.get('CELERY_TASK_SOFT_TIME_LIMIT', '1740'))
PIPELINE_RUN_STALE_AFTER_SECONDS = int(os.environ.get('PIPELINE_RUN_STALE_AFTER_SECONDS', '3600'))
PIPELINE_AUTO_DISPATCH = env_bool('PIPELINE_AUTO_DISPATCH', False)
# Security checks are opt-in until ClamAV is installed in the worker image.
# `optional` records an unavailable scanner as a review signal; `required`
# fails the pipeline when the scanner cannot be reached.
PIPELINE_ANTIVIRUS_MODE = os.environ.get('PIPELINE_ANTIVIRUS_MODE', 'disabled').strip().lower()
PIPELINE_ANTIVIRUS_TIMEOUT_SECONDS = int(os.environ.get('PIPELINE_ANTIVIRUS_TIMEOUT_SECONDS', '300'))
PIPELINE_STRICT_FILE_TYPES = env_bool('PIPELINE_STRICT_FILE_TYPES', False)
DIRECT_S3_UPLOADS = env_bool('DIRECT_S3_UPLOADS', True)
DIRECT_S3_UPLOAD_FALLBACK = env_bool('DIRECT_S3_UPLOAD_FALLBACK', True)
PAYMENT_WEBHOOK_SECRET = os.environ.get('PAYMENT_WEBHOOK_SECRET', '')
EXTERNAL_IMPORT_HMAC_SECRET = os.environ.get('EXTERNAL_IMPORT_HMAC_SECRET', '')
EXTERNAL_IMPORT_BUCKETS = [
    bucket.strip()
    for bucket in os.environ.get('EXTERNAL_IMPORT_BUCKETS', '').split(',')
    if bucket.strip()
]
EXTERNAL_IMPORT_MAX_BODY_BYTES = int(
    os.environ.get('EXTERNAL_IMPORT_MAX_BODY_BYTES', str(64 * 1024))
)


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # my apps
    'home.apps.HomeConfig',
    'account.apps.AccountConfig',
    'dataset.apps.DatasetConfig',
    'marketplace.apps.MarketplaceConfig',
    'djangoaddicts.pygwalker',
    'django_social_share',
    'taggit',
    'django.contrib.humanize',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'datahub_gui.urls'
LOGIN_URL = 'account:login'
LOGIN_REDIRECT_URL = 'home:home'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates']
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'datahub_gui.context_processors.ui',
            ],
        },
    },
]

WSGI_APPLICATION = 'datahub_gui.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

#DATABASES = {
#    'default': {
#        'ENGINE': 'django.db.backends.sqlite3',
#        'NAME': BASE_DIR / 'db.sqlite3',
#    }
#}


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get('DATABASE_NAME', 'datahub'),
        "USER": os.environ.get('DATABASE_USER', 'datahub'),
        "PASSWORD": os.environ.get('DATABASE_PASSWORD', ''),
        "HOST": os.environ.get('DATABASE_HOST', '127.0.0.1'),
        "PORT": os.environ.get('DATABASE_PORT', '5432'),
        "CONN_MAX_AGE": int(os.environ.get('DATABASE_CONN_MAX_AGE', '60')),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = os.environ.get('DJANGO_LANGUAGE_CODE', 'fa')
LANGUAGES = [
    ('fa', 'فارسی'),
    ('en', 'English'),
    ('ar', 'العربية'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
LANGUAGE_COOKIE_NAME = 'datahub_language'
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
LANGUAGE_COOKIE_SAMESITE = 'Lax'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = '/static/'
MEDIA_URL = '/media/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'assets')]
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', True)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
    SECURE_HSTS_PRELOAD = env_bool('DJANGO_SECURE_HSTS_PRELOAD', False)


# Ensure your storage backend handles paths correctly
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'


# Custom error handlers
handler403 = 'account.views.custom_permission_denied'
handler404 = 'account.views.custom_page_not_found'


CLOUD_STORAGE_CONFIG = {
    'S3_ENDPOINT': os.environ.get('S3_ENDPOINT', ''),
    'ACCESS_KEY': os.environ.get('S3_ACCESS_KEY', ''),
    'SECRET_KEY': os.environ.get('S3_SECRET_KEY', ''),
    'REGION': os.environ.get('S3_REGION', 'us-east-1'),
}
