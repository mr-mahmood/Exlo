import re
from datetime import date
from core.errors import APIError, UserProfileError, SignUpError, UserValidationError
from users.models import User


def validate_phone(value, instance=None):
    """
    Validate phone number.

    Unverified users get deleted to free up their phone number.
    Verified users block the number (it's taken).

    Note: No need to check "if user.pk == instance.pk" because:
    1. Same user, same number → caught by early return
    2. Same user, different number → impossible (unique constraint)
    3. New signup → instance is None
    """
    if not value:
        return value

    if not re.fullmatch(r"09\d{9}", value):
        raise APIError(UserValidationError.INVALID_PHONE_NUMBER)

    # Same user, same number → skip everything
    if instance and instance.phone_number == value:
        return value

    try:
        user: User = User.objects.get(phone_number=value)

        # Free up this number for the real owner
        if not user.is_verified:
            user.delete()
            return value

        # If verified, it's taken
        raise APIError(SignUpError.PHONE_NUMBER_REUSE)

    except User.DoesNotExist:
        return value


def validate_name(value):
    if not value or len(value.strip()) < 3:
        raise APIError(UserValidationError.INVALID_NAME)

    return value


def validate_date_of_birth(value):
    today = date.today()

    if value > today:
        raise APIError(UserProfileError.INVALID_DATE)

    return value
