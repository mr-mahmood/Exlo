# core/exceptions.py

from rest_framework import status
from rest_framework.exceptions import APIException


class APIError(APIException):
    def __init__(self, error, data=None):
        self.error_code = error[0]
        self.message = error[1]
        self.status_code = error[2]
        self.data = data

        super().__init__(
            detail=self.message,
            code=self.error_code,
        )


# ============================================================================
# AUTHENTICATION APP
# ============================================================================
class AuthSessionError(APIError):

    SESSION_EXPIRE = (
        "AUTH-001",
        "Session expired. Please log in again",
        status.HTTP_400_BAD_REQUEST,
    )

    COOKIES_NOT_PROVIDE = (
        "AUTH-002",
        "No cookies found in request",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# USERS APP
# ============================================================================
class UserAccountError(APIError):
    pass
