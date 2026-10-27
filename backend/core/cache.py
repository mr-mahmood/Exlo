# core/cache.py

from collections.abc import Callable
from typing import TypeVar
from urllib.parse import urlencode
from django.core.cache import cache
from django.db import transaction
T = TypeVar("T")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
CACHE_TIMEOUT = 300
CACHE_LOCK_TIMEOUT = 10
CACHE_LOCK_BLOCKING_TIMEOUT = 3
CACHE_MAX_VERSION = 1_000_000


# ---------------------------------------------------------------------------
# Cache namespaces
# ---------------------------------------------------------------------------
GYM_LIST = "gym:list"
GYM_DETAIL = "gym:detail"
GYM_PLANS = "gym:plans"
GYM_PHOTOS = "gym:photos"
GYM_ANNOUNCEMENTS = "gym:announcements"
GYM_USERS = "gym:users"
GYM_DEVICES = "gym:devices"
GYM_LOCKERS = "gym:lockers"

USER_SUBSCRIPTIONS = "user:subscriptions"
USER_SUBSCRIPTION = "user:subscription"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _base_key(namespace: str, *ids) -> str:
    if not ids:
        return namespace

    suffix = ":".join(str(value) for value in ids)
    return f"{namespace}:{suffix}"


def _version_key(namespace: str, *ids) -> str:
    return f"{_base_key(namespace, *ids)}:version"


def _get_version(namespace: str, *ids) -> int:
    key = _version_key(namespace, *ids)
    version = cache.get(key)

    if version is not None:
        return int(version)

    cache.add(key, 1, timeout=None)
    return int(cache.get(key) or 1)


def _bump_version(namespace: str, *ids) -> None:
    key = _version_key(namespace, *ids)
    cache.add(key, 1, timeout=None)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 2, timeout=None)


def _request_suffix(request) -> str:
    """
    Convert query parameters into a stable cache-key suffix.

    Examples:
        ?page=2&page_size=20
    and:
        ?page_size=20&page=2

    generate the same suffix.
    This means views do NOT need to manually understand pagination.
    """

    if request is None:
        return ""

    items = []

    for key in sorted(request.query_params.keys()):
        values = request.query_params.getlist(key)

        for value in sorted(values):
            items.append((key, value))

    if not items:
        return ""

    return urlencode(items)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def cache_key(namespace: str, *ids, request=None) -> str:
    """
    Build a versioned cache key.

    Examples:

        cache_key(GYM_LIST, request=request)
        -> gym:list:v1:page=1&page_size=20

        cache_key(GYM_DETAIL, 123)
        -> gym:detail:123:v4

        cache_key(GYM_ANNOUNCEMENTS, 123, request=request)
        -> gym:announcements:123:v2:page=3&page_size=20
    """

    base = _base_key(namespace, *ids)
    version = _get_version(namespace, *ids)

    key = f"{base}:v{version}"

    query = _request_suffix(request)

    if query:
        key = f"{key}:{query}"

    return key


def invalidate_cache(namespace: str, *ids) -> None:
    """
    Invalidate a namespace AFTER the current database transaction commits.

    Examples:

        invalidate(GYM_LIST)
        invalidate(GYM_DETAIL, gym.id)
        invalidate(GYM_PHOTOS, gym.id)
    """
    transaction.on_commit(lambda: _bump_version(namespace, *ids))


def get_cache(key: str, builder: Callable[[], T]) -> T:
    """
    Get a cached value.

    If missing:

        1. Acquire a Redis lock.
        2. Check cache again.
        3. One request builds the value.
        4. Cache it.
        5. Other requests reuse it.

    This prevents cache stampedes.
    Requires django-redis because cache.lock() is used.
    """

    # Fast path
    value = cache.get(key)

    if value is not None:
        return value

    lock = cache.lock(
        f"lock:{key}",
        timeout=CACHE_LOCK_TIMEOUT,
        blocking_timeout=CACHE_LOCK_BLOCKING_TIMEOUT,
    )
    acquired = lock.acquire(blocking=True)

    if acquired:
        try:
            # Another worker may have created the cache while
            # this request was waiting for the lock.
            value = cache.get(key)

            if value is not None:
                return value

            value = builder()

            cache.set(key, value, timeout=CACHE_TIMEOUT)
            return value
        finally:
            try:
                lock.release()
            except Exception:
                pass

    # We timed out waiting for the lock.
    # Check one last time because the lock owner may have finished
    # immediately before our timeout.
    value = cache.get(key)

    if value is not None:
        return value

    # Availability fallback.
    # Build it ourselves but DON'T cache it because another worker
    # may currently be rebuilding the authoritative entry.
    return builder()
