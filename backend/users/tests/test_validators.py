# users/tests/test_validators.py
from django.test import TestCase
from datetime import date, timedelta
from users.validators import validate_phone, validate_name, validate_date_of_birth
from users.models import User
from core.errors import APIError, UserValidationError, UserAccountError, SignUpError


class PhoneValidatorTest(TestCase):
    """Test phone number validator"""

    def test_valid_phone_numbers(self):
        """Test valid phone numbers"""
        valid_numbers = [
            "09123456789",
            "09987654321",
            "09111111111",
            "09222222222",
            "    09222222222    ",
        ]

        for phone in valid_numbers:
            result = validate_phone(phone)
            self.assertEqual(result, phone.strip())

    def test_invalid_phone_formats(self):
        """Test invalid phone formats"""
        invalid_numbers = [
            "0912345678",  # Too short
            "091234567890",  # Too long
            "01123456789",  # Wrong prefix
            "0912345678a",  # Contains letter
            "0922  2222222",
            "    0922  2222222",
            "",  # Empty
            None,  # None
            "1234567890",  # Wrong format
        ]

        for phone in invalid_numbers:
            with self.assertRaises(APIError) as context:
                validate_phone(phone)
            self.assertEqual(
                context.exception.error_code,
                UserValidationError.INVALID_PHONE_NUMBER[0],
            )

    def test_non_string_phone_numbers_are_rejected_without_queries(self):
        for phone in (
            9123456789,
            0,
            1.5,
            True,
            False,
            None,
            [],
            ["09123456789"],
            {},
            {"phone": "09123456789"},
            b"09123456789",
        ):
            with self.subTest(phone=phone), self.assertNumQueries(0):
                with self.assertRaises(APIError) as context:
                    validate_phone(phone)
                self.assertEqual(
                    context.exception.error_code,
                    UserValidationError.INVALID_PHONE_NUMBER[0],
                )

    def test_duplicate_phone_raises_error(self):
        """Test duplicate phone number raises error"""
        User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
        )

        with self.assertRaises(APIError) as context:
            validate_phone("09123456789")
        self.assertEqual(
            context.exception.error_code, SignUpError.PHONE_NUMBER_REUSE[0]
        )

    def test_same_user_phone_skip_validation(self):
        """Test same user with same phone passes validation"""
        user = User.objects.create_user(
            phone_number="09123456789", first_name="John", last_name="Doe"
        )

        result = validate_phone("09123456789", instance=user)
        self.assertEqual(result, "09123456789")


class NameValidatorTest(TestCase):
    """Test name validator"""

    def test_valid_names(self):
        """Test valid names"""
        valid_names = [
            "John  ",
            "   Jane",
            "   Ali   ",
            "Mohammad",
            " A23   ",  # Minimum length
            "John    Doe",
            "   John    Doe   ",  # Should become "John Doe"
            "  Seyed   Mohammad      Hosseini  ",  # Should become "Seyed Mohammad Hosseini"
            "جون   ",  # Unicode characters
        ]

        for name in valid_names:
            result = validate_name(name)
            expected = " ".join(name.strip().split())
            self.assertEqual(result, expected)

    def test_invalid_names(self):
        """Test invalid names"""
        invalid_names = [
            "",  # Empty
            " ",  # Space only
            "  ",  # Multiple spaces
            None,  # None
            "Ab   ",  # Too short (2 characters)
            "A    ",  # Already tested as valid? Check your logic
        ]

        for name in invalid_names:
            with self.assertRaises(APIError) as context:
                validate_name(name)
            self.assertEqual(
                context.exception.error_code, UserValidationError.INVALID_NAME[0]
            )


class DateOfBirthValidatorTest(TestCase):
    """Test date of birth validator"""

    def test_valid_dates(self):
        """Test valid dates"""
        valid_dates = [
            date(1990, 1, 1),
            date(2000, 12, 31),
            date(1950, 6, 15),
            date.today(),  # Today is valid
        ]

        for dob in valid_dates:
            result = validate_date_of_birth(dob)
            self.assertEqual(result, dob)

    def test_future_dates(self):
        """Test future dates raise error"""
        future_date = date.today() + timedelta(days=1)

        with self.assertRaises(APIError) as context:
            validate_date_of_birth(future_date)
        self.assertEqual(context.exception.error_code, UserAccountError.INVALID_DATE[0])

    def test_very_old_date(self):
        """Test very old date is valid"""
        old_date = date(1900, 1, 1)
        result = validate_date_of_birth(old_date)
        self.assertEqual(result, old_date)
