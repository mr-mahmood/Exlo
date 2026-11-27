from datetime import date
from core.errors import APIError, UserAccountError, SignUpError, UserValidationError
from users.models import User
from users.utils import normalize_phone


def validate_phone(value, instance=None, skip_duplicate_check=False):
    phone = normalize_phone(value)

    # Check for duplicates
    if not skip_duplicate_check:
        qs = User.objects.filter(phone_number=phone)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs:
            raise APIError(SignUpError.PHONE_NUMBER_REUSE)

    return phone


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
