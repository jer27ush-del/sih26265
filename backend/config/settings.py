"""Django settings. Secrets and database details come from environment variables (see .env.example)."""
import os
from pathlib import Path
from urllib.parse import urlsplit

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


def env_list(name, default=''):
    return [value.strip() for value in env(name, default).split(',') if value.strip()]


def _vercel_hostname(value):
    value = (value or '').strip()
    if not value or '*' in value:
        return None
    parsed = urlsplit(value if '://' in value else f'//{value}')
    if parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        return None
    return parsed.hostname


SECRET_KEY = env('DJANGO_SECRET_KEY', 'dev-only-change-me')
DEBUG = env_bool('DJANGO_DEBUG', False)
if not DEBUG and SECRET_KEY in ('', 'dev-only-change-me', 'replace-with-a-long-random-string'):
    raise RuntimeError('Set DJANGO_SECRET_KEY to a long random value before running with DJANGO_DEBUG=0.')
if not DEBUG and (len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5):
    raise RuntimeError('Production DJANGO_SECRET_KEY must be at least 50 characters and randomly generated.')
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
VERCEL_HOSTS = []
for _vercel_host_variable in ('VERCEL_URL', 'VERCEL_PROJECT_PRODUCTION_URL'):
    _vercel_host = _vercel_hostname(env(_vercel_host_variable, ''))
    if _vercel_host and _vercel_host not in VERCEL_HOSTS:
        VERCEL_HOSTS.append(_vercel_host)
    if _vercel_host and _vercel_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_vercel_host)

CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')
for _vercel_host in VERCEL_HOSTS:
    _vercel_origin = f'https://{_vercel_host}'
    if _vercel_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_vercel_origin)

# Demo-only switch: enables the one-click role switcher. Must be off in any real deployment.
DEMO_MODE = env_bool('FDR_DEMO_MODE', True)
IS_VERCEL = env_bool('VERCEL', False)

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
DB_ENGINE = env('DB_ENGINE', 'postgres').strip().lower()
if not DEBUG:
    if DB_ENGINE != 'postgres':
        raise RuntimeError('Production requires a persistent PostgreSQL database; SQLite is for local development only.')
    required_database_settings = ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_HOST')
    missing_database_settings = [name for name in required_database_settings if not env(name, '').strip()]
    if missing_database_settings:
        raise RuntimeError(
            'Set the production database environment variables: ' + ', '.join(missing_database_settings) + '.'
        )
    if env('POSTGRES_PASSWORD') in ('aicte', 'change-this-password'):
        raise RuntimeError('Replace the sample PostgreSQL password before running in production.')

if DB_ENGINE == 'sqlite':
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
elif DB_ENGINE == 'postgres':
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('POSTGRES_DB', 'aicte_fdr'),
        'USER': env('POSTGRES_USER', 'aicte'),
        'PASSWORD': env('POSTGRES_PASSWORD', 'aicte'),
        'HOST': env('POSTGRES_HOST', 'localhost'),
        'PORT': env('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': int(env('POSTGRES_CONN_MAX_AGE', '0' if IS_VERCEL else '60')),
    }}
else:
    raise RuntimeError("DB_ENGINE must be either 'postgres' or 'sqlite'.")

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

INSTALLED_APPS.insert(0, 'corsheaders')
MIDDLEWARE.insert(0, 'corsheaders.middleware.CorsMiddleware')
CORS_ALLOWED_ORIGINS = env_list('DJANGO_CORS_ALLOWED_ORIGINS')

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
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = int(env('DJANGO_SECURE_HSTS_SECONDS', '31536000'))
