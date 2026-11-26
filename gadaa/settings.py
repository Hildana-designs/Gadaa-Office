"""
GADAA settings.

Every secret and every machine-specific value comes from the environment or
from a settings file outside the code (data/gadaa.env by default). Nothing
secret is committed to Git.
"""
from pathlib import Path
import os

from gadaa.envfile import load_env_file, parse_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Where the database, uploaded files, backups and the settings file live.
DATA_DIR = Path(os.environ.get("GADAA_DATA_DIR", BASE_DIR / "data")).resolve()
ENV_FILE = Path(os.environ.get("GADAA_ENV_FILE", DATA_DIR / "gadaa.env"))
load_env_file(ENV_FILE)


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = env("GADAA_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "GADAA_SECRET_KEY is not set. Run 'python -m gadaa.bootstrap' "
        "(the installer does this for you)."
    )

# Key for passport and ID numbers (field-level encryption).
FIELD_ENCRYPTION_KEY = env("GADAA_FIELD_KEY", "")
# Key for backup files.
BACKUP_ENCRYPTION_KEY = env("GADAA_BACKUP_KEY", "")

DEBUG = env_bool("GADAA_DEBUG", False)
ALLOWED_HOSTS = [h.strip() for h in env("GADAA_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("GADAA_CSRF_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "core",
    "ops",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CurrentUserMiddleware",
    "core.middleware.LoginRequiredMiddleware",
]

ROOT_URLCONF = "gadaa.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "gadaa.wsgi.application"
ASGI_APPLICATION = "gadaa.asgi.application"

# Database: SQLite in the office, PostgreSQL later, chosen by GADAA_DATABASE_URL.
DATABASES = {
    "default": parse_database_url(
        env("GADAA_DATABASE_URL", ""), default_sqlite=DATA_DIR / "gadaa.sqlite3"
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

LANGUAGE_CODE = "en"
TIME_ZONE = env("GADAA_TIME_ZONE", "Africa/Addis_Ababa")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = DATA_DIR / "staticfiles"

# File storage goes through Django's storage layer so it can later point at
# object storage by changing configuration only.
MEDIA_ROOT = Path(env("GADAA_MEDIA_DIR", DATA_DIR / "files"))
MEDIA_URL = "/files/"
STORAGES = {
    "default": {
        "BACKEND": env("GADAA_FILE_STORAGE", "django.core.files.storage.FileSystemStorage"),
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "core:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:login"

# Sessions end after this many minutes without activity.
SESSION_COOKIE_AGE = int(env("GADAA_SESSION_MINUTES", "30")) * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Two-factor codes for staff. On by default.
GADAA_MFA_REQUIRED = env_bool("GADAA_MFA_REQUIRED", True)
OTP_TOTP_ISSUER = "GADAA Office"

# HTTPS on the office network (the start script serves HTTPS with a local certificate).
GADAA_HTTPS = env_bool("GADAA_HTTPS", True)
if GADAA_HTTPS:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Backups
BACKUP_DIR = Path(env("GADAA_BACKUP_DIR", DATA_DIR / "backups"))
# Second copy, ideally an external drive (for example E:\GADAA-backups).
BACKUP_OFFSITE_DIR = env("GADAA_BACKUP_OFFSITE_DIR", "")
BACKUP_HOUR = int(env("GADAA_BACKUP_HOUR", "19"))  # local time, 24h clock

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

FORMAT_MODULE_PATH = ["gadaa.formats"]
