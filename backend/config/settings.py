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
    "commerce_refunds",
    "commerce_commissions",
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

if DEBUG:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": dj_database_url.config(
            default=(
                f"postgresql://{os.getenv('POSTGRES_USER')}:"
                f"{os.getenv('POSTGRES_PASSWORD')}@"
                f"{os.getenv('POSTGRES_HOST')}:"
                f"{os.getenv('POSTGRES_PORT')}/"
                f"{os.getenv('POSTGRES_DB')}"
            ),
            conn_max_age=0,
            ssl_require=os.getenv("DB_SSL_REQUIRE", "False").lower() == "true",
        )
    }

    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# ============================================================================
# Auth
# ============================================================================
AUTH_USER_MODEL = "users.User"
AUTHENTICATION_BACKENDS = [
    "authentication.authentication.OTPAuthBackend",
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
        "anon": "100/min",  # Rate limit for unauthenticated users
        "user": "200/min",  # Rate limit for authenticated users
        "otp_phone": "5/day",
        "otp_ip": "10/day",
    },
    "EXCEPTION_HANDLER": "core.exception_handler.custom_exception_handler",
    # Date format
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S.%fZ",
    "DATE_FORMAT": "%Y-%m-%d",
    "TIME_FORMAT": "%H:%M:%S",
}

# ============================================================================
# JWT Settings
# ============================================================================
if DEBUG:
    SIMPLE_JWT = {
        "ACCESS_TOKEN_LIFETIME": timedelta(days=5),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
        "ROTATE_REFRESH_TOKENS": True,
        "BLACKLIST_AFTER_ROTATION": True,
        "AUTH_HEADER_TYPES": ("Bearer",),
        "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
        "USER_ID_FIELD": "id",
        "USER_ID_CLAIM": "key_1",
    }
else:
    SIMPLE_JWT = {
        "ACCESS_TOKEN_LIFETIME": timedelta(
            hours=int(os.getenv("JWT_ACCESS_HOURS", 1)),
        ),
        "REFRESH_TOKEN_LIFETIME": timedelta(
            days=int(os.getenv("JWT_REFRESH_DAYS", 15)),
        ),
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
if DEBUG:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }
else:
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
                "capacity": 1500,
                "expiry": 60,
                "group_expiry": 86400,
            },
        },
    }

# ============================================================================
# Caches
# ============================================================================
if DEBUG:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": (
                f"redis://:{os.getenv('REDIS_PASSWORD')}"
                f"@{os.getenv('REDIS_HOST')}:"
                f"{os.getenv('REDIS_PORT')}/1"
            ),
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "PARSER_CLASS": "redis.connection.HiredisParser",
                "CONNECTION_POOL_KWARGS": {
                    "max_connections": 20,
                    "retry_on_timeout": True,
                },
            },
            "TIMEOUT": 300,
        }
    }

# ============================================================================
# Celery
# ============================================================================
if DEBUG:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    # Use memory broker for development
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache"

    CELERY_TIMEZONE = TIME_ZONE
    CELERY_ENABLE_UTC = True
else:
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

    CELERY_TIMEZONE = TIME_ZONE
    CELERY_ENABLE_UTC = True

# ============================================
# CELERY BEAT
# ============================================
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "sweep-gym-subscriptions": {
        "task": "gym_subscriptions.tasks.sweep_gym_subscriptions",
        "schedule": crontab(hour=3, minute=0),
    },
    "delete-stale-gym-devices": {
        "task": "gym_devices.tasks.delete_stale_gym_devices",
        "schedule": crontab(hour=3, minute=10),
    },
}

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
            "level": "INFO",
        },
    },
}
