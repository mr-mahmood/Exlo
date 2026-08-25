import re
from datetime import date
from core.errors import APIError, UserAccountError, SignUpError, UserValidationError
from users.models import User


def validate_phone(value, instance=None, skip_duplicate_check=False):
    if value is None:
        raise APIError(UserValidationError.INVALID_PHONE_NUMBER)

    stripped_value = value.strip()

    # Validate format
    if not stripped_value or not re.fullmatch(r"09\d{9}", stripped_value):
        raise APIError(UserValidationError.INVALID_PHONE_NUMBER)

    # Check for duplicates
    if not skip_duplicate_check:
        qs = User.objects.filter(phone_number=stripped_value)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise APIError(SignUpError.PHONE_NUMBER_REUSE)

    return stripped_value


def validate_name(value):
    if not value or not value.strip():
        raise APIError(UserValidationError.INVALID_NAME)

    # Normalize: strip leading/trailing spaces and collapse internal spaces
    normalized_value = " ".join(value.strip().split())

    # Check length after normalization
    if len(normalized_value) < 3 or len(normalized_value) > 255:
        raise APIError(UserValidationError.INVALID_NAME)

    return normalized_value


def validate_date_of_birth(value):
    today = date.today()

    if value > today:
        raise APIError(UserAccountError.INVALID_DATE)

    return value
