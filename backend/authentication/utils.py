import secrets
import hashlib
import hmac
import re

from django.conf import settings
from django.core.cache import cache
from rest_framework.response import Response

SIGNUP_TTL = 600


def make_cookie(response: Response, cookies: dict, path="/", max_age=None) -> Response:
    for key, value in cookies.items():
        response.set_cookie(
            key=key,
            value=value,
            httponly=True,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite=settings.SESSION_COOKIE_SAMESITE,
            domain=settings.SESSION_COOKIE_DOMAIN,
            path=path,
            max_age=max_age,
        )
    return response


def delete_cookies(response: Response, names: list, path="/") -> Response:
    for name in names:
        response.delete_cookie(
            key=name,
            domain=settings.SESSION_COOKIE_DOMAIN,
            path=path,
            samesite=settings.SESSION_COOKIE_SAMESITE,
        )
    return response


def signup_key(phone_number):
    return f"signup_verified_{phone_number}"


def create_signup_proof(phone_number):
    token = secrets.token_urlsafe(32)

    cache.set(
        signup_key(phone_number),
        {
            "phone_number": phone_number,
            "proof_hash": hashlib.sha256(token.encode()).hexdigest(),
        },
        timeout=SIGNUP_TTL,
    )

    return token


def get_verified_signup_proof(phone_number, token):
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None

    record = cache.get(signup_key(phone_number))

    if not isinstance(record, dict):
        return None

    stored_hash = record.get("proof_hash")

    if record.get("phone_number") != phone_number or not isinstance(stored_hash, str):
        return None

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    return record if hmac.compare_digest(stored_hash, token_hash) else None
