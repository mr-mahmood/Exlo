# core/hashing.py

import hashlib
import hmac
from django.conf import settings

SCHEME = "hmac_sha256"
_SEPARATOR = "$"


def hash_secret(raw: str) -> str:
    digest = hmac.new(
        key=settings.SECRET_KEY.encode("utf-8"),
        msg=raw.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"{SCHEME}{_SEPARATOR}{digest}"


def verify_secret(raw: str, stored: str) -> bool:
    raw_hash = hash_secret(raw)
    return hmac.compare_digest(raw_hash, stored)
