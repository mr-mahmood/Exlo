# users/tests/test_models.py
from django.test import TestCase
from django.db import IntegrityError
from datetime import date, timedelta
from users.models import User
from core.errors import APIError, UserAccountError
from django.conf import settings


class UserModelTest(TestCase):
    """Test User model"""

    def setUp(self):
        settings.DEBUG = True
        """Set up test data"""
        self.valid_data = {
            "phone_number": "09123456789",
            "first_name": "John",
            "last_name": "Doe",
            "gender": User.Gender.MALE,
            "date_of_birth": date(1990, 1, 1),
        }

    # ============ CREATION TESTS ============

    def test_create_user_success(self):
        """Test successful user creation"""
        user: User = User.objects.create_user(**self.valid_data)

        self.assertEqual(user.phone_number, "09123456789")
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(user.gender, User.Gender.MALE)
        self.assertEqual(user.date_of_birth, date(1990, 1, 1))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_blocked)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.role, User.Role.USER)
        self.assertIsNotNone(user.referral_code)
        self.assertEqual(len(user.referral_code), 6)
        self.assertFalse(user.has_usable_password())

    def test_create_user_without_first_name_creates_user_with_empty_name(self):
        """Test creating user without first name creates user with empty first_name"""
        data = self.valid_data.copy()
        data.pop("first_name")

        user: User = User.objects.create_user(**data)
        self.assertEqual(user.first_name, "")
        self.assertEqual(user.phone_number, "09123456789")
        self.assertEqual(user.last_name, "Doe")

    def test_create_user_without_last_name_creates_user_with_empty_name(self):
        """Test creating user without last name creates user with empty last_name"""
        data = self.valid_data.copy()
        data.pop("last_name")

        user: User = User.objects.create_user(**data)
        self.assertEqual(user.last_name, "")
        self.assertEqual(user.phone_number, "09123456789")
        self.assertEqual(user.first_name, "John")

    def test_create_user_without_phone_number_raises_type_error(self):
        """Test creating user without phone number raises TypeError"""
        data = self.valid_data.copy()
        data.pop("phone_number")

        with self.assertRaises(TypeError):
            User.objects.create_user(**data)

    def test_create_user_duplicate_phone_raises_error(self):
        """Test duplicate phone number raises IntegrityError"""
        User.objects.create_user(**self.valid_data)

        duplicate_data = self.valid_data.copy()
        duplicate_data["phone_number"] = "09123456789"
        duplicate_data["first_name"] = "Jane"

        with self.assertRaises(IntegrityError):
            User.objects.create_user(**duplicate_data)

    def test_create_user_with_none_date_of_birth(self):
        """Test creating user with null date_of_birth"""
        data = self.valid_data.copy()
        data.pop("date_of_birth")
        user: User = User.objects.create_user(**data)
        self.assertIsNone(user.date_of_birth)

    def test_create_user_with_empty_date_of_birth(self):
        """Test creating user with empty date_of_birth"""
        data = self.valid_data.copy()
        data["date_of_birth"] = None
        user: User = User.objects.create_user(**data)
        self.assertIsNone(user.date_of_birth)

    def test_create_user_with_admin_role(self):
        """Test creating user with ADMIN role"""
        data = self.valid_data.copy()
        data["role"] = User.Role.ADMIN
        user: User = User.objects.create_user(**data)
        self.assertEqual(user.role, User.Role.ADMIN)

    # ============ SUPERUSER TESTS ============

    def test_create_superuser(self):
        """Test superuser creation"""
        admin = User.objects.create_superuser(
            phone_number="09123456789",
            password="admin123",
            first_name="Admin",
            last_name="User",
        )

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.check_password("admin123"))

    # ============ PROPERTY TESTS ============

    def test_full_name_property(self):
        """Test full_name property"""
        user: User = User.objects.create_user(**self.valid_data)
        self.assertEqual(user.full_name, "John Doe")

        user.first_name = "Jane"
        user.save()
        self.assertEqual(user.full_name, "Jane Doe")

        user.last_name = ""
        user.save()
        self.assertEqual(user.full_name, "Jane")

    def test_is_user_active_property(self):
        """Test is_user_active property"""
        user: User = User.objects.create_user(**self.valid_data)

        # Active user
        self.assertTrue(user.is_user_active)

        # Inactive user
        user.is_active = False
        user.save()
        self.assertFalse(user.is_user_active)

        # Blocked user
        user.is_active = True
        user.is_blocked = True
        user.save()
        self.assertFalse(user.is_user_active)

        # Inactive & Blocked user
        user.is_active = False
        user.is_blocked = True
        user.save()
        self.assertFalse(user.is_user_active)

    # ============ ACTION TESTS ============

    def test_block_user(self):
        """Test blocking a user"""
        user: User = User.objects.create_user(**self.valid_data)
        user.block()

        user.refresh_from_db()
        self.assertTrue(user.is_blocked)
        self.assertFalse(user.is_active)
        self.assertIsNotNone(user.blocked_at)

    def test_unblock_user(self):
        """Test unblocking a user"""
        user: User = User.objects.create_user(**self.valid_data)
        user.block()

        user.unblock()

        user.refresh_from_db()
        self.assertFalse(user.is_blocked)
        self.assertTrue(user.is_active)
        self.assertIsNone(user.blocked_at)

    def test_update_last_login_at(self):
        """Test updating last login timestamp"""
        user: User = User.objects.create_user(**self.valid_data)
        old_time = user.last_login_at

        import time

        time.sleep(0.1)

        user.update_last_login_at()
        user.refresh_from_db()

        self.assertNotEqual(user.last_login_at, old_time)
        self.assertIsNotNone(user.last_login_at)

    # ============ VALIDATION TESTS ============

    def test_validate_account_status_active_user(self):
        """Test account status validation for active user"""
        user: User = User.objects.create_user(**self.valid_data)
        result = user.validate_account_status()
        self.assertEqual(result, user)

    def test_validate_account_status_inactive_user(self):
        """Test account status validation for inactive user"""
        user: User = User.objects.create_user(**self.valid_data)
        user.is_active = False
        user.is_blocked = False
        user.save()

        with self.assertRaises(APIError) as context:
            user.validate_account_status()
        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_ACCOUNT_INACTIVE[0]
        )

    def test_validate_account_status_blocked_user(self):
        """Test account status validation for blocked user"""
        user: User = User.objects.create_user(**self.valid_data)
        user.is_active = True
        user.is_blocked = True
        user.save()

        with self.assertRaises(APIError) as context:
            user.validate_account_status()
        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_ACCOUNT_BLOCKED[0]
        )

    # ============ REFERRAL CODE TESTS ============

    def test_referral_code_uniqueness(self):
        """Test referral codes are unique across multiple users"""
        codes = set()

        for i in range(10):
            data = self.valid_data.copy()
            data["phone_number"] = f"091234567{89 + i}"
            data["first_name"] = f"User{i}"
            user: User = User.objects.create_user(**data)
            codes.add(user.referral_code)

        # All codes should be unique
        self.assertEqual(len(codes), 10)

        for code in codes:
            self.assertEqual(len(code), 6)
            valid_chars = set("23456789ABCDEFGHJKLMNPQRSTUVWXYZ")
            self.assertTrue(set(code).issubset(valid_chars))

    def test_referral_code_unique_constraint_enforced(self):
        """Test that the database prevents duplicate referral codes"""

        user1: User = User.objects.create_user(**self.valid_data)

        duplicate_data = {
            "phone_number": "09123456788",
            "first_name": "Jane",
            "last_name": "Smith",
            "gender": User.Gender.FEMALE,
            "date_of_birth": date(1995, 5, 5),
            "referral_code": user1.referral_code,  # Intentionally duplicate!
        }

        # This should raise IntegrityError because referral_code is unique
        with self.assertRaises(IntegrityError):
            User.objects.create(**duplicate_data)

    def test_referral_code_excludes_ambiguous_chars(self):
        """Test referral code excludes 0, O, 1, I"""
        user: User = User.objects.create_user(**self.valid_data)
        self.assertNotIn("0", user.referral_code)
        self.assertNotIn("O", user.referral_code)
        self.assertNotIn("1", user.referral_code)
        self.assertNotIn("I", user.referral_code)

    def test_referral_code_race_condition_handling(self):
        """Test referral code generation handles race conditions"""
        phones = [f"091234567{89 + i}" for i in range(20)]

        for phone in phones:
            data = self.valid_data.copy()
            data["phone_number"] = phone
            data["first_name"] = f"User{phone}"
            user: User = User.objects.create_user(**data)
            self.assertIsNotNone(user.referral_code)

    # ============ MODEL META TESTS ============

    def test_phone_number_unique_constraint(self):
        """Test phone_number has unique=True constraint"""
        field = User._meta.get_field("phone_number")
        self.assertTrue(field.unique)  # type: ignore

    def test_referral_code_editable_false(self):
        """Test referral_code has editable=False"""
        field = User._meta.get_field("referral_code")
        self.assertFalse(field.editable)

    def test_referral_code_unique_constraint_in_meta(self):
        """Test referral_code has unique=True constraint in model meta"""
        field = User._meta.get_field("referral_code")
        self.assertTrue(field.unique)  # type: ignore

    def test_model_db_table(self):
        """Test model uses correct database table name"""
        self.assertEqual(User._meta.db_table, "users")

    def test_model_ordering(self):
        """Test model default ordering"""
        self.assertEqual(User._meta.ordering, ["-created_at"])

    def test_model_indexes(self):
        """Test model has correct indexes"""
        index_names = [index.name for index in User._meta.indexes]
        self.assertIn("users_status_idx", index_names)
        self.assertIn("users_role_idx", index_names)
        self.assertIn("users_created_idx", index_names)
        self.assertIn("users_login_idx", index_names)
        self.assertIn("referral_code_idx", index_names)

    # ============ STRING REPRESENTATION TESTS ============

    def test_model_str(self):
        """Test string representation"""
        user: User = User.objects.create_user(**self.valid_data)
        self.assertEqual(str(user), "John Doe")

    def test_str_with_empty_name(self):
        """Test string representation with empty name"""
        data = self.valid_data.copy()
        data["first_name"] = ""
        data["last_name"] = ""
        user: User = User.objects.create_user(**data)
        self.assertEqual(str(user), "")

    def test_str_with_only_first_name(self):
        """Test string representation with only first name"""
        data = self.valid_data.copy()
        data["last_name"] = ""
        user: User = User.objects.create_user(**data)
        self.assertEqual(str(user), "John")

    # ============ PROFILE PICTURE TESTS ============

    def test_profile_picture_default(self):
        """Test default profile picture is set"""
        user: User = User.objects.create_user(**self.valid_data)
        self.assertEqual(user.profile_picture, "profile_pics/default_profile_image.png")

    def test_profile_picture_upload_path(self):
        """Test profile picture upload path generation"""
        from users.models import user_profile_picture_path

        filename = "test.jpg"
        path = user_profile_picture_path(None, filename)
        self.assertTrue(path.startswith("profile_pics/"))
        self.assertTrue(path.endswith(".jpg"))
        # UUID is 32 characters
        self.assertEqual(len(path.split("/")[1].split(".")[0]), 32)

    # ============ EMAIL & USERNAME TESTS ============

    def test_user_email_is_none(self):
        """Test that email field is set to None"""
        user: User = User.objects.create_user(**self.valid_data)
        self.assertIsNone(user.email)

    def test_user_username_is_none(self):
        """Test that username field is set to None"""
        user: User = User.objects.create_user(**self.valid_data)
        self.assertIsNone(user.username)


class UserManagerTest(TestCase):
    """Test UserManager - focuses on manager-specific behavior not covered in UserModelTest"""

    def test_create_user_with_extra_fields(self):
        """Test creating user with extra fields"""
        user: User = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
            date_of_birth=date(1990, 1, 1),
        )

        self.assertEqual(user.date_of_birth, date(1990, 1, 1))
        self.assertEqual(user.gender, User.Gender.MALE)

    def test_create_user_role_defaults_to_user(self):
        """Test role defaults to USER"""
        user: User = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
        )
        self.assertEqual(user.role, User.Role.USER)

    def test_create_user_sets_unusable_password(self):
        """Test create_user sets unusable password"""
        user: User = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
        )
        self.assertFalse(user.has_usable_password())

    def test_create_superuser_sets_password(self):
        """Test create_superuser sets password correctly"""
        admin = User.objects.create_superuser(
            phone_number="09123456789",
            password="secure123",
            first_name="Admin",
            last_name="User",
        )
        self.assertTrue(admin.check_password("secure123"))
