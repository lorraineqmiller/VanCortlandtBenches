import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

# Vercel sets VERCEL=1 plus the hostnames it serves each deployment on.
ON_VERCEL = bool(os.environ.get("VERCEL"))

DEBUG = os.environ.get("DJANGO_DEBUG", "0" if ON_VERCEL else "1") == "1"
# Empty when DEBUG is off and unset: settings still load (Vercel reads them at build
# time), but Django refuses to sign sessions or cookies until DJANGO_SECRET_KEY is set.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or ("dev-only-not-secret" if DEBUG else "")

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",") if h]
ALLOWED_HOSTS += [
    os.environ[k] for k in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL") if os.environ.get(k)
]
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1", "0.0.0.0")]
if ON_VERCEL:
    # Vercel terminates HTTPS and forwards plain HTTP.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "benches",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"



def _database_from_url(url):
    """DATABASE_URL / POSTGRES_URL as set by Vercel's Postgres integrations (e.g. Neon)."""
    u = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": u.path.lstrip("/"),
        "USER": unquote(u.username or ""),
        "PASSWORD": unquote(u.password or ""),
        "HOST": u.hostname,
        "PORT": str(u.port or 5432),
        "OPTIONS": dict(parse_qsl(u.query)),  # e.g. sslmode=require
    }


_db_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
DATABASES = {
    "default": _database_from_url(_db_url) if _db_url else {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "benches"),
        "USER": os.environ.get("POSTGRES_USER", "benches"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "benches"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Serve static files from the app directories, so no collectstatic step is needed at deploy time.
WHITENOISE_USE_FINDERS = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Send errors to stdout/stderr so they show up in Vercel's runtime logs even with DEBUG off.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")}},
}
