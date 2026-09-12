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
# SESSION
# ============================================================================
class SessionError(APIError):
    SESSION_EXPIRE = (
        "SESS_001",
        "Session expired.",
        status.HTTP_400_BAD_REQUEST,
    )

    SESSION_NOT_FOUND = (
        "SESS_002",
        "Session not found.",
        status.HTTP_404_NOT_FOUND,
    )

    NO_EXISTING_SESSION = (
        "SESS_003",
        "No Seccion found for User",
        status.HTTP_404_NOT_FOUND,
    )


# ============================================================================
# AUTHENTICATION
# ============================================================================
class AuthenticationError(APIError):
    SESSION_EXPIRE = (
        "AUTH_001",
        "Session expired. Please log in again",
        status.HTTP_400_BAD_REQUEST,
    )

    TOKEN_NOT_PROVIDE = (
        "AUTH_002",
        "No Token found in request",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_ACCESS_TOKEN = (
        "AUTH_003",
        "Invalid or malformed access token",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_REFRESH_TOKEN = (
        "AUTH_004",
        "Invalid or malformed refresh token",
        status.HTTP_400_BAD_REQUEST,
    )

    SESSION_NOT_FOUND = (
        "AUTH_005",
        "Session not found. Please log in again",
        status.HTTP_404_NOT_FOUND,
    )

    NO_REFRESH_TOKEN = (
        "AUTH_006",
        "No refresh token found in request",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# OTP ERRORS
# ============================================================================
class OTPError(APIError):
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
        "SIGN-001",
        "This phone number already exists",
        status.HTTP_400_BAD_REQUEST,
    )

    UNEXPECTED_ERROR = (
        "SIGN-002",
        "An unexpected error happened. Please try again.",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

    REFERRAL_CODE_NOT_VALID = (
        "SIGN-003",
        "referral code is not valid",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_GENDER = (
        "SIGN-004",
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
# User Account
# ============================================================================
class UserAccountError(APIError):
    USER_NOT_EXIST = (
        "USER-001",
        "User does not exist",
        status.HTTP_404_NOT_FOUND,
    )

    USER_ACCOUNT_INACTIVE = (
        "USER-002",
        "User account is inactive",
        status.HTTP_400_BAD_REQUEST,
    )

    USER_ACCOUNT_BLOCKED = (
        "USER-003",
        "User account is blocked",
        status.HTTP_400_BAD_REQUEST,
    )

    USER_NOT_VERIFIED = (
        "USER-004",
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

    INVALID_DATE = (
        "USER-007",
        "Date of birth cannot be in the future",
        status.HTTP_400_BAD_REQUEST,
    )

    PROFILE_PICTURE_TOO_LARGE = (
        "USER-008",
        f"Profile picture is too large",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_PROFILE_PICTURE_EXTENSION = (
        "USER-009",
        "Invalid file format",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_PROFILE_PICTURE = (
        "USER-010",
        "Invalid image file. Please upload a valid image",
        status.HTTP_400_BAD_REQUEST,
    )

    PROFILE_PICTURE_CONVERSION_FAILED = (
        "USER-011",
        "Failed to process profile picture. Please try with a different image",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# REFERRAL
# ============================================================================
class ReferralError(APIError):

    NO_EXISTING_REFERRAL = (
        "REFE_001",
        "No referral found for User",
        status.HTTP_404_NOT_FOUND,
    )

    SELF_REFERRAL_NOT_ALLOWED = (
        "REFE_002",
        "you cant referral your self",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# MEASUREMENTS
# ============================================================================
class MeasurementsError(APIError):

    NO_EXISTING_MEASUREMENTS = (
        "MEAS_001",
        "No measurement found for User",
        status.HTTP_404_NOT_FOUND,
    )

    MEASUREMENT_NOT_FOUND = (
        "MEAS_002",
        "requested measurement not found for User",
        status.HTTP_404_NOT_FOUND,
    )

    INVALID_HEIGHT = (
        "MEAS_003",
        "Height must be between 50 and 300 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_WEIGHT = (
        "MEAS_004",
        "Weight must be between 20 and 500 kg",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_CHEST = (
        "MEAS_008",
        "Chest circumference must be between 30 and 200 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_SHOULDERS = (
        "MEAS_009",
        "Shoulders circumference must be between 30 and 200 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_BICEPS = (
        "MEAS_010",
        "Biceps circumference must be between 10 and 80 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_FOREARMS = (
        "MEAS_011",
        "Forearms circumference must be between 10 and 60 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_WAIST = (
        "MEAS_012",
        "Waist circumference must be between 40 and 200 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_ABDOMEN = (
        "MEAS_013",
        "Abdomen circumference must be between 40 and 200 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_HIPS = (
        "MEAS_014",
        "Hips circumference must be between 40 and 200 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_QUADRICEPS = (
        "MEAS_015",
        "Quadriceps circumference must be between 20 and 100 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_CALVES = (
        "MEAS_016",
        "Calves circumference must be between 15 and 70 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_GLUTES = (
        "MEAS_017",
        "Glutes circumference must be between 40 and 200 cm",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_MUSCLE_MASS_EXCEEDS_WEIGHT = (
        "MEAS_018",
        "Muscle mass cannot exceed total body weight",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_BODY_FAT_FOR_WEIGHT = (
        "MEAS_019",
        "Body fat percentage seems too low for this weight",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_BICEPS_SYMMETRY = (
        "MEAS_020",
        "Left and right biceps difference seems too large (max 5cm difference allowed)",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_MEASUREMENT_DATE = (
        "MEAS_021",
        "Measurement date cannot be in the future",
        status.HTTP_400_BAD_REQUEST,
    )

    MISSING_MEASUREMENT_DATA = (
        "MEAS_022",
        "At least one measurement field is required",
        status.HTTP_400_BAD_REQUEST,
    )

    NO_EXISTING_MEASUREMENTS_PHOTOS = (
        "MEAS_023",
        "No measurement photos found for User and measurement",
        status.HTTP_404_NOT_FOUND,
    )

    MEASUREMENTS_PHOTO_TYPE_EXIST = (
        "MEAS_024",
        "This photo type already exists for this measurement",
        status.HTTP_400_BAD_REQUEST,
    )

    PHOTO_NOT_FOUND = (
        "MEAS_025",
        "Photo not found",
        status.HTTP_404_NOT_FOUND,
    )

    INVALID_PHOTO_TYPE = (
        "MEAS_026",
        "Invalid photo type",
        status.HTTP_400_BAD_REQUEST,
    )

    PHOTO_FILE_REQUIRED = (
        "MEAS_027",
        "Photo file is required",
        status.HTTP_400_BAD_REQUEST,
    )

    PHOTO_FILE_TOO_LARGE = (
        "MEAS_028",
        f"Photo file is too large",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_PHOTO_EXTENSION = (
        "MEAS_029",
        "Invalid file format",
        status.HTTP_400_BAD_REQUEST,
    )

    PHOTO_TYPE_REQUIRED = (
        "MEAS_030",
        "Photo type is required",
        status.HTTP_400_BAD_REQUEST,
    )

    IMAGE_CONVERSION_FAILED = (
        "MEAS_031",
        "Failed to process image. Please try with a different image",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# GYM
# ============================================================================
class GymError(APIError):
    GYM_NOT_FOUND = (
        "GYM_001",
        "gym not found",
        status.HTTP_404_NOT_FOUND,
    )

    GYM_HAS_ACTIVE_MEMBERSHIPS = (
        "GYM_002",
        "gym have active members in it still",
        status.HTTP_400_BAD_REQUEST,
    )

    PHOTO_NOT_FOUND = (
        "GYM_003",
        "photo not found",
        status.HTTP_404_NOT_FOUND,
    )

    PHOTO_FILE_TOO_LARGE = (
        "GYM_004",
        "photo file is too large",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_PHOTO_EXTENSION = (
        "GYM_005",
        "invalid photo extension",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_PHOTO_FILE = (
        "GYM_006",
        "invalid photo file",
        status.HTTP_400_BAD_REQUEST,
    )

    PHOTO_FILE_REQUIRED = (
        "GYM_007",
        "photo file is required",
        status.HTTP_400_BAD_REQUEST,
    )

    IMAGE_CONVERSION_FAILED = (
        "GYM_008",
        "failed to convert image to WebP format",
        status.HTTP_400_BAD_REQUEST,
    )

    PHOTO_UPLOAD_FAILED = (
        "GYM_009",
        "failed to upoad the images for gym",
        status.HTTP_400_BAD_REQUEST,
    )

    MISSING_GYM_DATA = (
        "GYM_010",
        "Some fields are required for gym create",
        status.HTTP_400_BAD_REQUEST,
    )

    PHOTO_FILE_EMPTY = (
        "GYM_011",
        "photo is empty",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# GYM ANNOUNCEMENT
# ============================================================================
class GymAnnouncementError(APIError):
    ANNOUNCEMENT_NOT_FOUND = (
        "ANNOU_001",
        "announcement not found",
        status.HTTP_404_NOT_FOUND,
    )

    GYM_REQUIRED = (
        "ANNOU_002",
        "gym is requierd for makign annoncement",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# GYM PLANS
# ============================================================================
class GymPlansError(APIError):
    PLAN_NOT_FOUND = (
        "PLAN_001",
        "Plan not found.",
        status.HTTP_404_NOT_FOUND,
    )
    INVALID_DURATION = (
        "PLAN_002",
        "Duration cannot be negative.",
        status.HTTP_400_BAD_REQUEST,
    )
    INVALID_VISIT_LIMIT = (
        "PLAN_003",
        "Visit limit cannot be negative.",
        status.HTTP_400_BAD_REQUEST,
    )
    INVALID_PRICE = (
        "PLAN_004",
        "Price cannot be negative.",
        status.HTTP_400_BAD_REQUEST,
    )


# ============================================================================
# GYM SUBSCRIPTIONs
# ============================================================================
class GymSubscriptionError(APIError):
    SUBSCRIPTION_NOT_FOUND = (
        "SUBS_001",
        "subscription not found.",
        status.HTTP_404_NOT_FOUND,
    )

    ACTIVE_SUBSCRIPTION_EXISTS = (
        "SUBS_002",
        "This user already has an active gym subscription",
        status.HTTP_400_BAD_REQUEST,
    )

    NO_ACTIVE_SUBSCRIPTION = (
        "SUBS_003",
        "This user has no active subscription",
        status.HTTP_400_BAD_REQUEST,
    )

    WRONG_GYM = (
        "SUBS_004",
        "This user has active subscription in a different gym",
        status.HTTP_400_BAD_REQUEST,
    )

    INVALID_ORDER_ITEM = (
        "SUBS_005",
        "This order item have no gym plan",
        status.HTTP_400_BAD_REQUEST,
    )
