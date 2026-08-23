import re
from datetime import date
from core.errors import APIError, UserProfileError, SignUpError, UserValidationError
from users.models import User


def validate_phone(value, instance=None):
    if not value:
        return value

    if not re.fullmatch(r"09\d{9}", value):
        raise APIError(UserValidationError.INVALID_PHONE_NUMBER)

    qs = User.objects.filter(phone_number=value)

    if instance is not None:
        qs = qs.exclude(pk=instance.pk)

    if User.objects.filter(phone_number=value).exists():
        raise APIError(SignUpError.PHONE_NUMBER_REUSE)

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
