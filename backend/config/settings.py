import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# ============================================================================
# Application environment
# ============================================================================
APP_ENV = os.getenv("APP_ENV", "development").lower()
IS_DEVELOPMENT = APP_ENV == "development"
IS_LOAD_TEST = APP_ENV == "apiloadtest"
IS_PRODUCTION = APP_ENV == "production"

# ============================================================================
# Base
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

PROJECT_ROOT = BASE_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")

DEBUG = APP_ENV == "development"
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
    # Auth apps
    "authentication",
    # User apps
    "users",
    "users_sessions",
    "users_referrals",
    "users_measurements",
    "users_nfc_cards",
    # Gym apps
    "gym",
    "gym_photos",
    "gym_announcements",
    "gym_auth",
    "gym_plans",
    "gym_subscriptions",
    "gym_visits",
    "gym_devices",
    "gym_locks",
    # Commerce apps
    "commerce_products",
    "commerce_orders",
    "commerce_payments",
    "commerce_payments_gateway",
    "commerce_refunds",
    "commerce_wallet",
    "commerce_wallet_ledger",
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
if not IS_PRODUCTION:
    MIDDLEWARE.insert(0, "core.middleware.RequestTimingMiddleware")

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
# DATABASE
# ============================================================================
import dj_database_url

POSTGRES_HOST = "localhost" if IS_DEVELOPMENT else "pgbouncer"
POSTGRES_PORT = "5432" if IS_DEVELOPMENT else "6432"
POSTGRES_USER = os.getenv("POSTGRES_USER", "exlo")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_DB = os.getenv("POSTGRES_DB", "exlo")

DATABASES = {
    "default": dj_database_url.config(
        default=(f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@" f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"),
        conn_max_age=0,
        ssl_require=False,
    )
}
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# ============================================================================
# Auth
# ============================================================================
AUTH_USER_MODEL = "users.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
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
    # Authentication
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "authentication.authentication.AccessTokenAuthentication",
    ],
    # Permissions
    "DEFAULT_PERMISSION_CLASSES": [
        "authentication.permissions.IsUserActive",
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
    # Throttling
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",  # For unauthenticated users
        "rest_framework.throttling.UserRateThrottle",  # For authenticated users
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/min" if IS_PRODUCTION else "10000000/day",
        "user": "200/min" if IS_PRODUCTION else "10000000/day",
        "otp_phone": "5/day" if IS_PRODUCTION else "10000000/day",
        "otp_ip": "10/day" if IS_PRODUCTION else "100000000/day",
    },
    "EXCEPTION_HANDLER": "core.exception_handler.custom_exception_handler",
    # Date format
    "DATETIME_FORMAT": "iso-8601",
    "DATE_FORMAT": "%Y-%m-%d",
    "TIME_FORMAT": "%H:%M:%S",
}

# ============================================================================
# JWT Settings
# ============================================================================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        hours=int(os.getenv("JWT_ACCESS_HOURS", 1)),
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.getenv("JWT_REFRESH_DAYS", 15)),
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "key_1",
}

# ============================================================================
# Channels & Caches & Celery
# ============================================================================
REDIS_HOST = "localhost" if IS_DEVELOPMENT else "redis"
REDIS_PORT = "6379"
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"],
            "capacity": 1500,
            "expiry": 60,
            "group_expiry": 86400,
        },
    },
}


CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_CLASS": "redis.BlockingConnectionPool",
            "IGNORE_EXCEPTIONS": False,
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 150,
                "timeout": 1,
            },
        },
        "TIMEOUT": 300,
    }
}


CELERY_BROKER_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/2"
CELERY_RESULT_BACKEND = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/3"

CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_WORKER_MAX_TASKS_PER_CHILD = 500
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_BROKER_CONNECTION_TIMEOUT = 30
CELERY_BROKER_HEARTBEAT = 30
CELERY_BROKER_POOL_LIMIT = 10

# ============================================
# CELERY BEAT
# ============================================
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "sweep-gym-subscriptions": {
        "task": "gym_subscriptions.tasks.sweep_gym_subscriptions",
        "schedule": crontab(hour=3, minute=0),
    },
    "cleanup-expired-user-sessions": {
        "task": "users_sessions.tasks.cleanup_expired_sessions",
        "schedule": crontab(hour=3, minute=10),
    },
    "process-approved-refunds": {
        "task": "commerce_refunds.tasks.process_pending_refunds",
        "schedule": crontab(hour=3, minute=20),
    },
    "process-seller-settlements": {
        "task": "commerce_orders.tasks.process_seller_settlements",
        "schedule": crontab(hour=3, minute=30),
    },
}

# ============================================================================
# Cookies & CORS
# ============================================================================
CORS_EXPOSE_HEADERS = ["Retry-After"]

if IS_PRODUCTION:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    USE_X_FORWARDED_PORT = True

    # Production settings (example domain.com)
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
else:
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

# ============================================================================
# File Upload
# ============================================================================
# Limit file upload size
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Allowed image types
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# ============================================================================
# Zibal Payment Gateway Settings
# ============================================================================
ZIBAL_MERCHANT = os.getenv("ZIBAL_MERCHANT")
ZIBAL_API_TOKEN = os.getenv("ZIBAL_API_TOKEN")
ZIBAL_ACCOUNT_ID = os.getenv("ZIBAL_ACCOUNT_ID")
ZIBAL_IPG_FEE_MAX = 250_000  # Rial
ZIBAL_EBANK_FEE_MAX = 600_000  # Rial

# ============================================================================
# Sms.ir
# ============================================================================
SMSIR_API_KEY = os.getenv("SMSIR_API_KEY")

# ============================================================================
# OTP
# ============================================================================
OTP_EXPIRY_SECONDS = 120
OTP_MAX_ATTEMPTS = 5

# ============================================================================
# Logging
# ============================================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
