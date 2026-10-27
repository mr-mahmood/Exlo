import secrets
from django.conf import settings
from django.core.cache import cache
from core.errors import APIError, OTPError
from core.hashing import hash_secret, verify_secret

OTP_CACHE_PREFIX = "otp"
OTP_EXPIRY_SECONDS = 120


def generate_otp(phone_number: str):

    # Generate secure OTP
    if settings.IS_PRODUCTION:
        otp_code = str(secrets.randbelow(900000) + 100000)
    else:
        otp_code = "123456"

    # Hash the OTP before storing
    hashed_otp = hash_secret(otp_code)

    # Store HASHED OTP
    cache_key = f"{OTP_CACHE_PREFIX}_{phone_number}"
    cache.set(cache_key, hashed_otp, OTP_EXPIRY_SECONDS)

    # Send OTP via SMS
    if settings.IS_PRODUCTION:
        from core.sms_task import send_sms_verification_task

        send_sms_verification_task.delay(phone_number, otp_code)

    # Delete plain OTP text from memory
    del otp_code

    return True


def verify_otp(phone_number: str, otp_code: str):

    # Get hashed OTP from cache
    cache_key = f"{OTP_CACHE_PREFIX}_{phone_number}"
    stored_hash = cache.get(cache_key)

    if not stored_hash:
        raise APIError(OTPError.OTP_NOT_FOUND)

    # Verify OTP using constant-time comparison (PREVENT Timing Attack)
    if verify_secret(otp_code, stored_hash):
        # Success
        cache.delete(cache_key)
        return True
    else:
        raise APIError(OTPError.OTP_INVALID)
