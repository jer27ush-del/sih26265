"""Django settings. Secrets and database details come from environment variables (see .env.example)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Reads KEY=VALUE lines from backend/.env into the environment. Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / '.env')


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


SECRET_KEY = env('DJANGO_SECRET_KEY', 'dev-only-change-me')
DEBUG = env_bool('DJANGO_DEBUG', True)
if not DEBUG and SECRET_KEY in ('', 'dev-only-change-me', 'replace-with-a-long-random-string'):
    raise RuntimeError('Set DJANGO_SECRET_KEY to a long random value before running with DJANGO_DEBUG=0.')
ALLOWED_HOSTS = [h.strip() for h in env('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]
# Demo-only switch: enables the one-click role switcher. Must be off in any real deployment.
DEMO_MODE = env_bool('FDR_DEMO_MODE', True)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'fdr',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': ['django.template.context_processors.request',
                                       'django.contrib.auth.context_processors.auth',
                                       'django.contrib.messages.context_processors.messages']},
}]
WSGI_APPLICATION = 'config.wsgi.application'

# Database: PostgreSQL by default (as the spec requires). SQLite is offered only for a quick local demo.
if env('DB_ENGINE', 'postgres') == 'sqlite':
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
else:
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('POSTGRES_DB', 'aicte_fdr'),
        'USER': env('POSTGRES_USER', 'aicte'),
        'PASSWORD': env('POSTGRES_PASSWORD', 'aicte'),
        'HOST': env('POSTGRES_HOST', 'localhost'),
        'PORT': env('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': 60,
    }}

AUTH_USER_MODEL = 'fdr.User'

# Argon2 first, as the spec recommends. Falls back to Django's default if the package is not installed.
def _argon2_usable():
    """True only if the native Argon2 library actually works here (import alone is not enough)."""
    try:
        from argon2 import PasswordHasher
        PasswordHasher().hash('probe')
        return True
    except Exception:
        return False


PASSWORD_HASHERS = (
    (['django.contrib.auth.hashers.Argon2PasswordHasher'] if _argon2_usable() else [])
    + ['django.contrib.auth.hashers.PBKDF2PasswordHasher']
)
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
]

LANGUAGE_CODE = 'en-in'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = False
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Uploaded documents live outside the public web folder and are served only through a permission-checked API.
PRIVATE_MEDIA_ROOT = Path(env('PRIVATE_MEDIA_ROOT', str(BASE_DIR / 'private_media')))
DOCUMENT_MAX_BYTES_DEFAULT = 10 * 1024 * 1024

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.TokenAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_PARSER_CLASSES': ['rest_framework.parsers.JSONParser', 'rest_framework.parsers.MultiPartParser'],
    'EXCEPTION_HANDLER': 'fdr.errors.exception_handler',
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {'anon': '60/minute'},
}

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(env('EMAIL_PORT', '25'))
EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
EMAIL_TIMEOUT = int(env('EMAIL_TIMEOUT', '10'))
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'AICTE FDR Portal <fdr-portal@localhost>')
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise RuntimeError('EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled.')

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', True)
