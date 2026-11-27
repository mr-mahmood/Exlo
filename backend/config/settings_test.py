from .settings import *
from django.core.exceptions import ImproperlyConfigured

if not IS_DEVELOPMENT:
    raise ImproperlyConfigured("Exlo tests require APP_ENV=development.")

DEBUG = True

# Redis DBs 0–3 serve Channels, the development cache, and Celery.
# Reserve DB 4 for sequential tests and DB 4 + worker ID for parallel tests.
TEST_RUNNER = "config.redis_tests.RedisTestRunner"
CACHES = {
    "default": {
        **CACHES["default"],
        "BACKEND": "config.redis_tests.WorkerRedisCache",
        "LOCATION": CACHES["default"]["LOCATION"].rsplit("/", 1)[0] + "/4",
    }
}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
