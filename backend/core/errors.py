import stat

from rest_framework import status
from rest_framework.exceptions import APIException


class APIError(APIException):
    def __init__(self, error, data=None):
        self.error_code = error[0]
        self.message = error[1]
        self.status_code = error[2]

        self.detail = {
            "error_code": error[0],
            "error_message": error[1],
        }


# ============================================================================
# AUTHENTICATION & SESSION ERRORS
# ============================================================================
class AuthSessionError(APIError):
    SESSION_EXPIRE = (
        "SES-001",
        "Session expired. Please log in again",
        status.HTTP_400_BAD_REQUEST,
    )

    COOKIES_NOT_PROVIDE = (
        "SES-002",
        "No cookies found in request",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_ACCESS_TOKEN = (
        "SES-003",
        "Invalid or malformed access token",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_REFRESH_TOKEN = (
        "SES-004",
        "Invalid or malformed refresh token",
        status.HTTP_400_BAD_REQUEST,
    )

    SESSION_NOT_FOUND = (
        "SES-005",
        "Session not found. Please log in again",
        status.HTTP_404_NOT_FOUND,
    )

    NO_REFRESH_TOKEN = (
        "SES-007",
        "No refresh token found in request",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# OTP ERRORS
# ============================================================================
class AuthOTPError(APIError):
    PHONE_REQUIRED = (
        "OTP-001",
        "Phone number is required",
        status.HTTP_400_BAD_REQUEST,
    )

    OTP_NOT_FOUND = (
        "OTP-002",
        "OTP not found or expired",
        status.HTTP_404_NOT_FOUND,
    )

    OTP_INVALID = (
        "OTP-003",
        "Invalid OTP code",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_STEP = (
        "OTP-004",
        "Invalid flow step. Please start the phone change process again.",
        status.HTTP_400_BAD_REQUEST,
    )

    OLD_PHONE_VERIFICATION_REQUIRED = (
        "OTP-005",
        "Current phone verification is required before changing to a new number.",
        status.HTTP_400_BAD_REQUEST,
    )

    NEW_PHONE_NOT_FOUND = (
        "OTP-006",
        "New phone number not found in session. Please request OTP again.",
        status.HTTP_400_BAD_REQUEST,
    )

    OLD_PHONE_OTP_FAILED = (
        "OTP-007",
        "Failed to send OTP to current phone number.",
        status.HTTP_400_BAD_REQUEST,
    )

    NEW_PHONE_OTP_FAILED = (
        "OTP-008",
        "Failed to send OTP to new phone number.",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# Validation Errors
# ============================================================================
class UserValidationError(APIError):
    INVALID_PHONE_NUMBER = (
        "VAL-001",
        "Phone number must start with 09 and be 11 digits",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_NAME = (
        "VAL-002",
        "First and last name must be at least 3 characters and lower than 255",
        status.HTTP_400_BAD_REQUEST,
    )

    FIRST_NAME_REQUIRED = (
        "VAL-004",
        "First name is required",
        status.HTTP_400_BAD_REQUEST,
    )

    LAST_NAME_REQUIRED = (
        "VAL-005",
        "Last name is required",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# Sign Up
# ============================================================================
class SignUpError(APIError):
    PHONE_NUMBER_REUSE = (
        "SIG-001",
        "This phone number already exists",
        status.HTTP_400_BAD_REQUEST,
    )

    UNEXPECTED_ERROR = (
        "SIG-002",
        "An unexpected error happened. Please try again.",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

    REFERRAL_CODE_NOT_VALID = (
        "SIG-003",
        "referral code is not valid",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_GENDER = (
        "SIG-004",
        "Gender is not valid",
        status.HTTP_400_BAD_REQUEST,
    )

    SIGN_UP_NOT_ALLOWED = (
        "SIGN-005",
        "sign up is not allowed before phone verification",
        status.HTTP_400_BAD_REQUEST,
    )

    PHONE_REQUIRED = (
        "SIGN-006",
        "Phone number is required",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# User Profile
# ============================================================================
class UserProfileError(APIError):
    INVALID_DATE = (
        "PRO-001",
        "Date of birth cannot be in the future",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# User Account
# ============================================================================
class UserAccountError(APIError):
    USER_NOT_EXIST = (
        "ACT-001",
        "User does not exist",
        status.HTTP_404_NOT_FOUND,
    )

    USER_ACCOUNT_INACTIVE = (
        "ACT-002",
        "User account is inactive",
        status.HTTP_400_BAD_REQUEST,
    )

    USER_ACCOUNT_BLOCKED = (
        "ACT-003",
        "User account is blocked",
        status.HTTP_400_BAD_REQUEST,
    )

    USER_NOT_VERIFIED = (
        "ACT-004",
        "User account is not verified",
        status.HTTP_400_BAD_REQUEST,
    )

    PHONE_ALREADY_EXISTS = (
        "USER-005",
        "This phone number is already in use",
        status.HTTP_400_BAD_REQUEST,
    )

    SAME_PHONE_AS_CURRENT = (
        "USER-006",
        "This is already your current phone number",
        status.HTTP_400_BAD_REQUEST,
    )
