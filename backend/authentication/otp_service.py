import secrets
import hashlib
import hmac
from django.conf import settings
from django.core.cache import cache
from core.sms_task import send_sms_verification_task
from core.errors import APIError, AuthOTPError

OTP_CACHE_PREFIX = "otp"
OTP_EXPIRY_SECONDS = 120


def generate_otp(phone_number: str):

    # Generate secure OTP
    if settings.DEBUG:
        otp_code = "123456"
    else:
        otp_code = str(secrets.randbelow(900000) + 100000)

    # Hash the OTP before storing
    hashed_otp = _hash_otp(otp_code)

    # Store HASHED OTP
    cache_key = f"{OTP_CACHE_PREFIX}_{phone_number}"
    cache.set(cache_key, hashed_otp, OTP_EXPIRY_SECONDS)

    # Send OTP via SMS
    if not settings.DEBUG:
        send_sms_verification_task.delay(phone_number, otp_code)

    # Delete plain OTP text from memory
    del otp_code

    return True


def verify_otp(phone_number: str, otp_code: str):

    # Get hashed OTP from cache
    cache_key = f"{OTP_CACHE_PREFIX}_{phone_number}"
    stored_hash = cache.get(cache_key)

    if not stored_hash:
        raise APIError(AuthOTPError.OTP_NOT_FOUND)

    # Hash the input OTP and compare with stored hash
    hashed_input = _hash_otp(otp_code)

    # Verify OTP using constant-time comparison (PREVENT Timing Attack)
    if hmac.compare_digest(hashed_input, stored_hash):
        # Success
        cache.delete(cache_key)
    else:
        raise APIError(AuthOTPError.OTP_INVALID)


def _hash_otp(otp_code: str) -> str:
    """Hash OTP code using HMAC-SHA256"""
    return hmac.new(
        key=settings.SECRET_KEY.encode("utf-8"),
        msg=otp_code.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
