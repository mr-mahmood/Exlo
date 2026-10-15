# users/tests/test_serializers.py
from typing import cast
from django.conf import settings
from django.test import TestCase
from django.db import IntegrityError
from datetime import date, timedelta
from rest_framework.exceptions import ValidationError as DRFValidationError
from users.serializers import UserSignupSerializer, UserProfileSerializer
from users.models import User
from core.errors import APIError, UserValidationError, SignUpError, UserAccountError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io
import os


class UserSignupSerializerTest(TestCase):
    """Test UserSignupSerializer"""

    def setUp(self):
        settings.DEBUG = True
        self.valid_data = {
            "phone_number": "09123456789",
            "first_name": "John",
            "last_name": "Doe",
            "gender": User.Gender.MALE,
            "date_of_birth": date(1990, 1, 1),
        }

    def test_valid_data(self):
        """Test serializer with valid data"""
        serializer = UserSignupSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())
        user = cast(User, serializer.save())

        self.assertEqual(user.phone_number, "09123456789")
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(user.gender, User.Gender.MALE)
        self.assertEqual(user.date_of_birth, date(1990, 1, 1))

    # --- Required fields ---

    def test_missing_phone_number(self):
        data = self.valid_data.copy()
        data.pop("phone_number")
        serializer = UserSignupSerializer(data=data)
        with self.assertRaises(DRFValidationError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertIn("phone_number", context.exception.detail)

    def test_missing_first_name(self):
        data = self.valid_data.copy()
        data.pop("first_name")
        serializer = UserSignupSerializer(data=data)
        with self.assertRaises(DRFValidationError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertIn("first_name", context.exception.detail)

    def test_missing_last_name(self):
        data = self.valid_data.copy()
        data.pop("last_name")
        serializer = UserSignupSerializer(data=data)
        with self.assertRaises(DRFValidationError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertIn("last_name", context.exception.detail)

    def test_missing_gender(self):
        data = self.valid_data.copy()
        data.pop("gender")
        serializer = UserSignupSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("gender", serializer.errors)

    def test_missing_date_of_birth(self):
        data = self.valid_data.copy()
        data.pop("date_of_birth")
        serializer = UserSignupSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("date_of_birth", serializer.errors)

    # --- Custom validation (one representative test each) ---

    def test_invalid_phone_format(self):
        data = self.valid_data.copy()
        data["phone_number"] = "invalid"
        serializer = UserSignupSerializer(data=data)
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, UserValidationError.INVALID_PHONE_NUMBER[0]
        )

    def test_invalid_first_name_too_short(self):
        data = self.valid_data.copy()
        data["first_name"] = "Jo"
        serializer = UserSignupSerializer(data=data)
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, UserValidationError.INVALID_NAME[0]
        )

    def test_future_date_of_birth(self):
        data = self.valid_data.copy()
        data["date_of_birth"] = date.today() + timedelta(days=1)
        serializer = UserSignupSerializer(data=data)
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(context.exception.error_code, UserAccountError.INVALID_DATE[0])

    def test_duplicate_phone(self):
        User.objects.create_user(
            phone_number="09123456789",
            first_name="Existing",
            last_name="User",
            gender=User.Gender.MALE,
        )
        data = self.valid_data.copy()
        data["phone_number"] = "09123456789"
        serializer = UserSignupSerializer(data=data)
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, SignUpError.PHONE_NUMBER_REUSE[0]
        )

    # --- Referral handling ---

    def test_no_referral_code(self):
        data = self.valid_data.copy()
        data.pop("referral", None)
        serializer = UserSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("referral"))  # type: ignore

    def test_empty_referral_code(self):
        data = self.valid_data.copy()
        data["referral"] = ""
        serializer = UserSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("referral"))  # type: ignore

    def test_referral_code_whitespace(self):
        data = self.valid_data.copy()
        data["referral"] = "   "
        serializer = UserSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("referral"))  # type: ignore

    def test_valid_referral_code(self):
        existing_user = User.objects.create_user(
            phone_number="09123456700",
            first_name="Existing",
            last_name="User",
            gender=User.Gender.MALE,
            date_of_birth="1990-01-01",
        )
        data = self.valid_data.copy()
        data["referral"] = existing_user.referral_code
        serializer = UserSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["referral"], existing_user.referral_code)  # type: ignore

    def test_invalid_referral_code(self):
        data = self.valid_data.copy()
        data["referral"] = "INVALID123"
        serializer = UserSignupSerializer(data=data)
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, SignUpError.REFERRAL_CODE_NOT_VALID[0]
        )

    # --- Normalization and read-only ---

    def test_name_with_leading_trailing_spaces(self):
        data = self.valid_data.copy()
        data["first_name"] = "  John  "
        data["last_name"] = "  Doe  "
        serializer = UserSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["first_name"], "John")  # type: ignore
        self.assertEqual(serializer.validated_data["last_name"], "Doe")  # type: ignore

    def test_phone_with_whitespace(self):
        data = self.valid_data.copy()
        data["phone_number"] = " 09123456789 "
        serializer = UserSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["phone_number"], "09123456789")  # type: ignore

    def test_referral_read_only_fields(self):
        data = self.valid_data.copy()
        data["referral_code"] = "CUSTOM123"
        data["profile_picture"] = "custom.jpg"
        serializer = UserSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        user = cast(User, serializer.save())
        self.assertNotEqual(user.referral_code, "CUSTOM123")
        self.assertIsNotNone(user.referral_code)

    def test_mass_assignment_protection(self):
        data = self.valid_data.copy()
        data["role"] = User.Role.ADMIN
        data["is_staff"] = True
        data["is_superuser"] = True
        data["is_verified"] = True
        data["is_active"] = False
        serializer = UserSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        user = cast(User, serializer.save())
        self.assertEqual(user.role, User.Role.USER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)

    # --- Race condition handling ---

    def test_race_condition_handling(self):
        User.objects.create_user(
            phone_number="09123456789",
            first_name="User1",
            last_name="Test",
            gender=User.Gender.MALE,
        )
        data = {
            "phone_number": "09123456788",
            "first_name": "User2",
            "last_name": "Test",
            "gender": User.Gender.MALE,
            "date_of_birth": date(1990, 1, 1),
        }
        serializer = UserSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        original_create_user = User.objects.create_user

        def mock_create_user(**kwargs):
            raise IntegrityError("Duplicate referral code")

        try:
            User.objects.create_user = mock_create_user  # type: ignore
            with self.assertRaises(APIError) as context:
                serializer.save()
            self.assertEqual(
                context.exception.error_code, SignUpError.UNEXPECTED_ERROR[0]
            )
        finally:
            User.objects.create_user = original_create_user

    # --- Output structure ---

    def test_serializer_returns_expected_fields(self):
        serializer = UserSignupSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())
        user = cast(User, serializer.save())
        output_serializer = UserSignupSerializer(user)
        output_data = output_serializer.data

        expected_fields = [
            "phone_number",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "referral_code",
            "profile_picture",
        ]
        for field in expected_fields:
            self.assertIn(field, output_data)

        self.assertNotIn("referral", output_data)
        self.assertNotIn("password", output_data)

    def test_serializer_with_extra_fields_ignored(self):
        data = self.valid_data.copy()
        data["extra_field"] = "should_be_ignored"
        serializer = UserSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertNotIn("extra_field", serializer.validated_data)  # type: ignore


class UserProfileSerializerTest(TestCase):
    """Test UserProfileSerializer"""

    def setUp(self):
        settings.DEBUG = True
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
            date_of_birth=date(1990, 1, 1),
        )

    def test_serialize_user(self):
        serializer = UserProfileSerializer(self.user)
        data = serializer.data
        self.assertEqual(data["phone_number"], "09123456789")  # type: ignore
        self.assertEqual(data["first_name"], "John")  # type: ignore
        self.assertEqual(data["last_name"], "Doe")  # type: ignore
        self.assertEqual(data["gender"], User.Gender.MALE)  # type: ignore
        self.assertEqual(data["date_of_birth"], "1990-01-01")  # type: ignore
        self.assertEqual(data["referral_code"], self.user.referral_code)  # type: ignore

    def test_update_user(self):
        data = {
            "first_name": "Jane",
            "last_name": "Smith",
            "gender": User.Gender.FEMALE,
            "date_of_birth": date(1995, 5, 5),
        }
        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        updated_user = cast(User, serializer.save())
        self.assertEqual(updated_user.first_name, "Jane")
        self.assertEqual(updated_user.last_name, "Smith")
        self.assertEqual(updated_user.gender, User.Gender.FEMALE)
        self.assertEqual(updated_user.date_of_birth, date(1995, 5, 5))

    def test_read_only_fields(self):
        data = {"phone_number": "09999999999", "referral_code": "NEWCODE"}
        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        user = cast(User, serializer.save())
        self.assertEqual(user.phone_number, "09123456789")
        self.assertEqual(user.referral_code, self.user.referral_code)

    def test_invalid_first_name_update(self):
        data = {"first_name": "Jo"}
        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, UserValidationError.INVALID_NAME[0]
        )

    def test_invalid_date_of_birth_update(self):
        data = {"date_of_birth": date.today() + timedelta(days=1)}
        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(context.exception.error_code, UserAccountError.INVALID_DATE[0])

    def test_partial_update_single_field(self):
        data = {"first_name": "Jane"}
        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        user = cast(User, serializer.save())
        self.assertEqual(user.first_name, "Jane")
        self.assertEqual(user.last_name, "Doe")

    def test_partial_update_empty_data(self):
        serializer = UserProfileSerializer(self.user, data={}, partial=True)
        self.assertTrue(serializer.is_valid())
        user = cast(User, serializer.save())
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")

    def test_same_phone_update(self):
        data = {"phone_number": "09123456789"}
        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        user = cast(User, serializer.save())
        self.assertEqual(user.phone_number, "09123456789")

    def test_update_to_other_existing_phone(self):
        other_user = User.objects.create_user(
            phone_number="09999999999",
            first_name="Other",
            last_name="User",
            gender=User.Gender.FEMALE,
            date_of_birth=date(1990, 1, 1),
        )
        data = {"phone_number": "09999999999"}
        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        updated_user = cast(User, serializer.save())
        self.assertEqual(updated_user.phone_number, "09123456789")
        self.assertNotEqual(updated_user.phone_number, other_user.phone_number)

    def test_update_name_with_whitespace(self):
        data = {"first_name": "  Jane  ", "last_name": "  Smith  "}
        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        user = cast(User, serializer.save())
        self.assertEqual(user.first_name, "Jane")
        self.assertEqual(user.last_name, "Smith")


class UserProfilePictureSerializerTest(TestCase):
    """Test UserProfileSerializer with profile picture handling"""

    def setUp(self):
        settings.DEBUG = True
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
            date_of_birth=date(1990, 1, 1),
        )
        self.test_image = self.create_test_image()

    def create_test_image(self, format="JPEG", size=(100, 100)):
        """Create a test image"""
        image = Image.new("RGB", size, color="red")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format=format)
        image_bytes.seek(0)

        ext = "jpg" if format == "JPEG" else format.lower()
        return SimpleUploadedFile(
            f"test.{ext}", image_bytes.read(), content_type=f"image/{ext}"
        )

    def test_update_profile_picture_converts_to_webp(self):
        """Test that profile picture is converted to WebP on update"""
        data = {
            "profile_picture": self.test_image,
        }

        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        updated_user = cast(User, serializer.save())

        # Check that the file is saved as WebP
        self.assertTrue(updated_user.profile_picture.name.endswith(".webp"))  # type: ignore

        # Verify it's a valid WebP image using PIL
        img = Image.open(updated_user.profile_picture)
        self.assertEqual(img.format, "WEBP")

    def test_update_profile_picture_with_png_converts_to_webp(self):
        """Test that PNG profile picture is converted to WebP"""
        png_image = self.create_test_image(format="PNG")

        data = {
            "profile_picture": png_image,
        }

        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        updated_user = cast(User, serializer.save())

        self.assertTrue(updated_user.profile_picture.name.endswith(".webp"))  # type: ignore

        img = Image.open(updated_user.profile_picture)
        self.assertEqual(img.format, "WEBP")

    def test_update_profile_picture_invalid_extension(self):
        """Test updating profile picture with invalid file extension"""
        invalid_file = SimpleUploadedFile(
            "test.txt", b"This is not an image", content_type="text/plain"
        )

        data = {
            "profile_picture": invalid_file,
        }

        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn("profile_picture", serializer.errors)
        self.assertEqual(
            str(serializer.errors["profile_picture"][0]),  # type: ignore
            "Upload a valid image. The file you uploaded was either not an image or a corrupted image.",
        )

    def test_update_profile_picture_too_large(self):
        """Test updating profile picture with file too large"""
        # Create a large file
        large_image = self.create_test_image(size=(2000, 2000))
        # Make it larger by setting size to exceed limit
        large_image.size = settings.MAX_IMAGE_SIZE + 1 # type: ignore

        data = {
            "profile_picture": large_image,
        }

        serializer = UserProfileSerializer(self.user, data=data, partial=True)

        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, UserAccountError.PROFILE_PICTURE_TOO_LARGE[0]
        )

    def test_update_profile_picture_corrupted_image(self):
        """Test updating profile picture with corrupted image"""
        corrupted_file = SimpleUploadedFile(
            "corrupted.jpg",
            b"This is not a valid image content",
            content_type="image/jpeg",
        )

        data = {
            "profile_picture": corrupted_file,
        }

        serializer = UserProfileSerializer(self.user, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn("profile_picture", serializer.errors)
        self.assertEqual(
            str(serializer.errors["profile_picture"][0]),  # type: ignore
            "Upload a valid image. The file you uploaded was either not an image or a corrupted image.",
        )
