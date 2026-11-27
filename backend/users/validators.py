from datetime import date
from core.errors import APIError, UserAccountError, SignUpError, UserValidationError
from users.models import User


def validate_phone(normalized_phone, instance=None):
    """Reject a canonical phone number already assigned to another user."""
    users = User.objects.filter(phone_number=normalized_phone)
    if instance is not None:
        users = users.exclude(pk=instance.pk)
    if users.exists():
        raise APIError(SignUpError.PHONE_NUMBER_REUSE)
    return normalized_phone


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
