from unicodedata import decimal

from core.errors import APIError, UserValidationError


def normalize_phone(value):
    phone = value.strip() if isinstance(value, str) else ""
    if len(phone) != 11 or not phone.isdecimal():
        raise APIError(UserValidationError.INVALID_PHONE_NUMBER)
    if not phone.isascii():
        phone = "".join(str(decimal(digit)) for digit in phone)
    if not phone.startswith("09"):
        raise APIError(UserValidationError.INVALID_PHONE_NUMBER)
    return phone
