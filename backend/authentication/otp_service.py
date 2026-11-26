import secrets
from enum import StrEnum
from math import ceil
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from kombu.exceptions import EncodeError, OperationalError
from redis.exceptions import RedisError, WatchError

from core.errors import APIError, OTPError
from core.hashing import hash_secret, verify_secret
from users.validators import validate_phone

MAX_WATCH_RETRIES = 3


class OTPPurpose(StrEnum):
    LOGIN = "login"
    OLD_PHONE = "old_phone"
    NEW_PHONE = "new_phone"


def _otp_key(phone_number, purpose, user_id):
    purpose = OTPPurpose(purpose)
    return f"otp:{purpose}:{user_id or '-'}:{phone_number}"


def _retry_after(ttl_ms):
    return max(1, ceil((ttl_ms or 0) / 1000))


def _is_watch_conflict(exc):
    # redis-py also raises WatchError when the connection drops during EXEC.
    return (
        isinstance(exc, WatchError)
        and exc.args == ("Watched variable changed.",)
        and not isinstance(exc.__cause__, RedisError)
        and not isinstance(exc.__context__, RedisError)
    )


def _cancel_challenge(cache_key, expected_challenge):
    """Cancel only the exact, unchanged challenge."""

    try:
        client = cache.client.get_client(write=True)
        key = cache.make_key(cache_key)
        with client.pipeline() as pipe:
            pipe.watch(key)

            current = pipe.get(key)

            if current is None:
                return False

            if cache.client.decode(current) != expected_challenge:
                return False

            pipe.multi()
            pipe.delete(key)

            return bool(pipe.execute()[0])

    except RedisError:
        return False


def generate_otp(*, phone_number: str, purpose: OTPPurpose, user_id=None) -> None:

    phone_number = validate_phone(phone_number, skip_duplicate_check=True)
    cache_key = _otp_key(phone_number, purpose, user_id)

    if settings.IS_PRODUCTION:
        from core.sms_task import send_sms_verification_task

        otp_code = str(secrets.randbelow(900000) + 100000)
    else:
        otp_code = "123456"

    challenge = (uuid4().hex, hash_secret(otp_code), 0)

    # TODO: Reserve paid SMS quotas together with challenge creation using Redis
    # WATCH/MULTI/EXEC without Lua. Across login and phone changes, allow 10 sends
    # per validated destination in any 24 hours and 30 per trusted Nginx client IP
    # in any hour. Add a configurable global cap per Tehran calendar day to protect
    # provider credit. Rejected sends and verification consume no SMS quota.
    # Preserve the resend cooldown and verification attempt limit.
    # Atomic SET NX with expiration through django-redis.

    try:
        created = cache.add(cache_key, challenge, timeout=settings.OTP_EXPIRY_SECONDS)
        if not created:
            raise APIError(OTPError.OTP_ALREADY_ACTIVE, retry_after=_retry_after(cache.pttl(cache_key)))
    except RedisError:
        raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)

    if settings.IS_PRODUCTION:
        try:
            send_sms_verification_task.delay(phone_number, otp_code)
        except EncodeError:
            _cancel_challenge(cache_key, challenge)
            raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)
        except (OperationalError, RedisError):
            raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)


def verify_otp(*, phone_number: str, otp_code: str, purpose: OTPPurpose, user_id=None) -> None:

    phone_number = validate_phone(phone_number, skip_duplicate_check=True)
    cache_key = _otp_key(phone_number, purpose, user_id)

    max_attempts = settings.OTP_MAX_ATTEMPTS
    original_challenge_id = None

    for _ in range(MAX_WATCH_RETRIES + 1):
        executing = False
        try:
            client = cache.client.get_client(write=True)
            key = cache.make_key(cache_key)
            with client.pipeline() as pipe:

                # Monitor the key before reading it.
                pipe.watch(key)

                raw_challenge = pipe.get(key)

                if raw_challenge is None:
                    raise APIError(OTPError.OTP_NOT_FOUND)

                challenge = cache.client.decode(raw_challenge)

                # Reject records using the previous storage format.
                if not isinstance(challenge, tuple) or len(challenge) != 3:
                    raise APIError(OTPError.OTP_NOT_FOUND)

                challenge_id, stored_hash, failures = challenge
                if original_challenge_id is None:
                    original_challenge_id = challenge_id
                elif challenge_id != original_challenge_id:
                    raise APIError(OTPError.OTP_NOT_FOUND)

                if failures >= max_attempts:
                    ttl_ms = pipe.pttl(key)
                    if ttl_ms == -2:
                        raise APIError(OTPError.OTP_NOT_FOUND)
                    raise APIError(OTPError.OTP_ATTEMPTS_EXHAUSTED, retry_after=_retry_after(ttl_ms))

                # Already consumed.
                if stored_hash is None:
                    raise APIError(OTPError.OTP_NOT_FOUND)

                valid = (
                    isinstance(otp_code, str)
                    and len(otp_code) == 6
                    and otp_code.isascii()
                    and otp_code.isdigit()
                    and verify_secret(otp_code, stored_hash)
                )

                if valid:
                    # Consume the OTP but preserve its resend cooldown.
                    updated_challenge = (challenge_id, None, failures)
                else:
                    failures += 1
                    updated_challenge = (challenge_id, None if failures >= max_attempts else stored_hash, failures)

                # Queue the conditional update.
                pipe.multi()
                pipe.set(key, cache.client.encode(updated_challenge), xx=True, keepttl=True)
                pipe.pttl(key)

                # Redis commits only if the watched key is unchanged.
                executing = True
                updated, ttl_ms = pipe.execute()
                executing = False

                if not updated:
                    raise APIError(OTPError.OTP_NOT_FOUND)

                if valid:
                    return

                if failures >= max_attempts:
                    raise APIError(OTPError.OTP_ATTEMPTS_EXHAUSTED, retry_after=_retry_after(ttl_ms))

                raise APIError(OTPError.OTP_INVALID)

        except RedisError as exc:
            if executing:
                if _is_watch_conflict(exc):
                    continue
            raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)

    raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)
