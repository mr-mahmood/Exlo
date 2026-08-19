import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# Base
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost", "domain.com"]

# ============================================================================
# Applications
# ============================================================================
INSTALLED_APPS = [
    # Base apps
    "daphne",
    "corsheaders",
    "channels",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "import_export",
    # Project apps
    "users",
    "authentication",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# ============================================================================
# Templates
# ============================================================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ============================================================================
# WSGI & ASGI
# ============================================================================
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ============================================================================
# DATABASE CONFIGURATION (Single Database)
# ============================================================================
import dj_database_url

DATABASE_URL = f"postgres://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

DATABASES = {
    "default": dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=False,
    )
}

# Production performance optimizations
if not DEBUG:
    DATABASES["default"]["OPTIONS"] = {
        # Connection timeout
        "connect_timeout": 10,
        # TCP Keepalive - prevents stale connections
        "keepalives": 1,
        "keepalives_idle": 60,  # Send keepalive after 60s idle
        "keepalives_interval": 30,  # Send keepalive every 30s
        "keepalives_count": 5,  # Drop connection after 5 failures
        # Statement timeout - kills slow queries
        "options": "-c statement_timeout=15s",
        # Client encoding
        "client_encoding": "UTF8",
    }

# ============================================================================
# Auth
# ============================================================================
AUTH_USER_MODEL = "users.User"
AUTHENTICATION_BACKENDS = [
    "authentication.backends.OTPAuthBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ============================================================================
# Internationalization
# ============================================================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# ============================================================================
# Static & Media
# ============================================================================
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "static"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================================
# REST Framework
# ============================================================================
REST_FRAMEWORK = {
    # Pagination
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    # Authentication
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "authentication.auth.VersionedJWTAuthentication",
    ],
    # Permissions
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Renderers - Only JSON
    "DEFAULT_RENDERER_CLASSES": [
        "core.renderers.GlobalJSONRenderer",
    ],
    # Parser classes - Only JSON and File uploads
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    # Date format
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S.%fZ",
    "DATE_FORMAT": "%Y-%m-%d",
    "TIME_FORMAT": "%H:%M:%S",
}

# ============================================================================
# JWT Settings
# ============================================================================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=int(os.getenv("JWT_ACCESS_HOURS", 1))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", 15))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "key_1",
}

# ============================================================================
# Channels
# ============================================================================
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                (
                    f"redis://:{os.getenv('REDIS_PASSWORD')}"
                    f"@{os.getenv('REDIS_HOST')}:"
                    f"{os.getenv('REDIS_PORT')}/0"
                )
            ],
            # Performance
            "capacity": 1500,
            "expiry": 60,
            "group_expiry": 86400,
        },
    },
}

# ============================================================================
# Caches
# ============================================================================
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://:{os.getenv('REDIS_PASSWORD')}@{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "PARSER_CLASS": "redis.connection.HiredisParser",  # Faster
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 20,
                "retry_on_timeout": True,
            },
        },
        "TIMEOUT": 300,  # Default cache timeout
    }
}

# ============================================================================
# Celery
# ============================================================================
CELERY_BROKER_URL = f"redis://:{os.getenv('REDIS_PASSWORD')}@{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/2"
CELERY_RESULT_BACKEND = f"redis://:{os.getenv('REDIS_PASSWORD')}@{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/3"

# Time limits
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4 minutes soft limit

# Worker settings
CELERY_WORKER_MAX_TASKS_PER_CHILD = 500  # Prevent memory leaks
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Fair distribution
CELERY_TASK_ACKS_LATE = True  # Acknowledge after execution

# Connection settings
CELERY_BROKER_CONNECTION_TIMEOUT = 30
CELERY_BROKER_HEARTBEAT = 30
CELERY_BROKER_POOL_LIMIT = 10

# ============================================================================
# Cookies & CORS
# ============================================================================
if DEBUG:
    # Development settings (localhost)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False  # Allow HTTP on localhost
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_DOMAIN = None  # localhost doesn't need domain
    CSRF_COOKIE_SECURE = False  # Allow HTTP on localhost
    CSRF_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_DOMAIN = None

    # CORS/CSRF for localhost
    CSRF_TRUSTED_ORIGINS = [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    CORS_ALLOWED_ORIGINS = [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    CORS_ALLOW_CREDENTIALS = True

else:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    USE_X_FORWARDED_PORT = True

    # Production settings (domain.com)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True  # HTTPS only
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_DOMAIN = ".domain.com"
    CSRF_COOKIE_SECURE = True  # HTTPS only
    CSRF_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_DOMAIN = ".domain.com"

    # Production origins
    CSRF_TRUSTED_ORIGINS = [
        "https://domain.com",
        "https://www.domain.com",
        "https://api.domain.com",
        "https://admin.domain.com",
    ]
    CORS_ALLOWED_ORIGINS = [
        "https://domain.com",
        "https://www.domain.com",
        "https://admin.domain.com",
    ]
    CORS_ALLOW_CREDENTIALS = True

    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"

# ============================================================================
# File Upload
# ============================================================================
# Limit file upload size
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Allowed image types (for your app)
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# ============================================================================
# Zibal Payment Gateway Settings
# ============================================================================
ZIBAL_MERCHANT = os.getenv("ZIBAL_MERCHANT")

# ============================================================================
# Sms.ir
# ============================================================================
SMSIR_API_KEY = os.getenv("SMSIR_API_KEY")


# ============================================================================
# Logging
# ============================================================================
LOG_DIR = BASE_DIR / "logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO" if not DEBUG else "DEBUG",
        },
    },
}
