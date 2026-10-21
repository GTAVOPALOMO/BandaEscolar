import os
from pathlib import Path

import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent
IS_VERCEL = bool(os.getenv("VERCEL"))
DEBUG = os.getenv("DEBUG", "0").lower() in {"1", "true", "yes"}
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY es obligatoria cuando DEBUG no está activo")

ALLOWED_HOSTS = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]

# En Vercel este directorio solo se usa para temporales. Nunca contiene datos
# persistentes: PostgreSQL y Supabase Storage son las fuentes duraderas.
DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp/banda-escolar" if IS_VERCEL else BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "common", "accounts", "students", "dues", "cash", "events", "tickets", "audit",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.ForcePasswordChangeMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
              "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL and not DEBUG:
    message = "DATABASE_URL es obligatoria en Vercel" if IS_VERCEL else "DATABASE_URL es obligatoria fuera del desarrollo local"
    raise RuntimeError(message)

if DATABASE_URL:
    database_ssl_required = os.getenv("DATABASE_SSL_REQUIRE", "1").lower() in {"1", "true", "yes"}
    if not DEBUG and not database_ssl_required:
        raise RuntimeError("SSL de PostgreSQL no puede desactivarse en producción")
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=0, ssl_require=database_ssl_required)}
    DATABASES["default"]["CONN_MAX_AGE"] = 0
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
    DATABASES["default"].setdefault("OPTIONS", {}).update({
        "sslmode": "require" if database_ssl_required else "disable",
        # Supabase Transaction Pooler no admite prepared statements con nombre.
        "prepare_threshold": None,
    })
else:
    # SQLite es únicamente la alternativa cómoda para desarrollo y pruebas locales.
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("DATABASE_PATH", DATA_DIR / "db.sqlite3"),
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "es-cr"
TIME_ZONE = "America/Costa_Rica"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

USE_SUPABASE_STORAGE = os.getenv("USE_SUPABASE_STORAGE", "0" if DEBUG and not IS_VERCEL else "1").lower() in {"1", "true", "yes"}
if not DEBUG and not USE_SUPABASE_STORAGE:
    raise RuntimeError("Supabase Storage es obligatorio en producción; no hay almacenamiento local persistente")

if USE_SUPABASE_STORAGE:
    storage_env = {
        "access_key": os.getenv("SUPABASE_S3_ACCESS_KEY_ID"),
        "secret_key": os.getenv("SUPABASE_S3_SECRET_ACCESS_KEY"),
        "endpoint_url": os.getenv("SUPABASE_S3_ENDPOINT_URL"),
        "region_name": os.getenv("SUPABASE_S3_REGION_NAME"),
    }
    missing = [name for name, value in {
        "SUPABASE_S3_ACCESS_KEY_ID": storage_env["access_key"],
        "SUPABASE_S3_SECRET_ACCESS_KEY": storage_env["secret_key"],
        "SUPABASE_S3_ENDPOINT_URL": storage_env["endpoint_url"],
        "SUPABASE_S3_REGION_NAME": storage_env["region_name"],
    }.items() if not value]
    if missing:
        raise RuntimeError(f"Faltan variables de Supabase Storage: {', '.join(missing)}")
    default_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **storage_env,
            "bucket_name": "eventos",
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": int(os.getenv("EVENT_IMAGE_URL_TTL", "300")),
            "signature_version": "s3v4",
            "addressing_style": "path",
            "file_overwrite": False,
        },
    }
else:
    default_storage = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": DATA_DIR / "media"},
    }

STORAGES = {
    "default": default_storage,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG else "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
EVENT_IMAGE_URL_TTL = int(os.getenv("EVENT_IMAGE_URL_TTL", "300"))
MEDIA_URL = "/media/"
MEDIA_ROOT = DATA_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "0" if DEBUG else "1") == "1"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# El cuerpo multipart añade bytes al archivo. 4 MiB deja margen frente al límite
# de 4.5 MB por solicitud de las Functions de Vercel.
MAX_EVENT_IMAGE_BYTES = 4 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_EVENT_IMAGE_BYTES
DATA_UPLOAD_MAX_MEMORY_SIZE = 4_500_000
if IS_VERCEL:
    FILE_UPLOAD_TEMP_DIR = "/tmp"
