# users/tests/test_views.py
# type: ignore

from django.conf import settings
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from datetime import date, timedelta
from unittest.mock import patch
from core.errors import SignUpError, UserAccountError
from users.models import User
from users_sessions.models import Session
from authentication.otp_service import OTP_CACHE_PREFIX
from core.errors import AuthenticationError, SignUpError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io


class UserSignupViewTest(TestCase):
    """Test user signup view"""

    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()
        cache.clear()
        self.url = reverse("users:user-signup")

        # Simulate phone verification
        self.verified_phone = "09123456789"
        cache.set(
            f"signup_verified_{self.verified_phone}",
            {"phone_number": self.verified_phone},
            600,
        )

        self.valid_data = {
            "phone_number": self.verified_phone,
            "first_name": "John",
            "last_name": "Doe",
            "gender": User.Gender.MALE,
            "date_of_birth": date(1990, 1, 1),
        }

    def tearDown(self):
        cache.clear()

    # ========== SUCCESS CASES ==========

    def test_signup_success(self):
        """Test successful signup with all valid data"""
        response = self.client.post(self.url, self.valid_data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("user", response.data)  # type: ignore

        user = User.objects.get(phone_number=self.valid_data["phone_number"])
        self.assertEqual(user.first_name, self.valid_data["first_name"])
        self.assertEqual(user.last_name, self.valid_data["last_name"])
        self.assertEqual(user.gender, self.valid_data["gender"])
        self.assertEqual(user.date_of_birth, self.valid_data["date_of_birth"])
        self.assertIsNotNone(user.referral_code)
        self.assertTrue(user.is_active)

        # Check session created
        self.assertTrue(Session.objects.filter(user=user).exists())
        session = Session.objects.get(user=user)
        self.assertIsNotNone(session.id)
        self.assertEqual(session.ip_address, "127.0.0.1")

        # Check cookies set
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertTrue(response.cookies["access_token"]["httponly"])
        self.assertTrue(response.cookies["refresh_token"]["httponly"])

        # Check cache cleared
        self.assertIsNone(
            cache.get(f"signup_verified_{self.valid_data['phone_number']}")
        )

    def test_signup_success_with_referral(self):
        """Test successful signup with valid referral code"""
        referrer = User.objects.create_user(
            phone_number="09123456788",
            first_name="Referrer",
            last_name="User",
            gender=User.Gender.MALE,
        )

        data = self.valid_data.copy()
        data["referral"] = referrer.referral_code

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        from users_referrals.models import Referral

        user = User.objects.get(phone_number=self.valid_data["phone_number"])
        referral = Referral.objects.get(referred_user=user)
        self.assertEqual(referral.referrer, referrer)
        self.assertIsNotNone(referral.referred_at)

    # ========== PHONE VERIFICATION TESTS ==========

    def test_signup_without_phone_verification(self):
        """Test signup without prior phone verification"""
        cache.clear()
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], SignUpError.SIGN_UP_NOT_ALLOWED[0])  # type: ignore

    def test_signup_with_expired_phone_verification(self):
        """Test signup with expired phone verification"""
        cache.set(
            f"signup_verified_{self.verified_phone}",
            {"phone_number": self.verified_phone},
            -1,
        )
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_signup_with_wrong_phone_verification(self):
        """Test signup with phone number that wasn't verified"""
        data = self.valid_data.copy()
        data["phone_number"] = "09123456788"
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ========== VALIDATION (single representative) ==========

    def test_signup_missing_fields(self):
        """Test signup with missing required fields"""
        required_fields = [
            "phone_number",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
        ]

        for field in required_fields:
            data = self.valid_data.copy()
            data.pop(field)
            response = self.client.post(self.url, data)
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Field '{field}' should be required",
            )

    def test_signup_invalid_phone(self):
        """Test signup with an invalid phone number format (single case)"""
        data = self.valid_data.copy()
        data["phone_number"] = "12345"  # invalid

        verified_key = f"signup_verified_{data['phone_number']}"
        cache.set(
            verified_key,
            {"phone_number": data["phone_number"]},
            600,
        )
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ========== DUPLICATE TESTS ==========
    def test_signup_duplicate_phone(self):
        """Test signup with phone number already in use"""
        User.objects.create_user(
            phone_number=self.valid_data["phone_number"],
            first_name="Existing",
            last_name="User",
            gender=User.Gender.MALE,
        )

        verified_key = f"signup_verified_{self.valid_data["phone_number"]}"
        cache.set(
            verified_key,
            {"phone_number": self.valid_data["phone_number"]},
            600,
        )
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], SignUpError.PHONE_NUMBER_REUSE[0])  # type: ignore

    # ========== REFERRAL TESTS ==========
    def test_signup_with_invalid_referral(self):
        """Test signup with invalid referral code"""
        data = self.valid_data.copy()
        data["referral"] = "INVALID_CODE"

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], SignUpError.REFERRAL_CODE_NOT_VALID[0])  # type: ignore

    # ========== EDGE CASES ==========
    def test_signup_with_special_characters_in_name(self):
        """Test signup with special characters in name"""
        data = self.valid_data.copy()
        data["first_name"] = "John-Doe"
        data["last_name"] = "O'Brien"
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user: User = User.objects.get(phone_number=self.valid_data["phone_number"])
        self.assertEqual(user.first_name, "John-Doe")
        self.assertEqual(user.last_name, "O'Brien")

    def test_signup_with_unicode_characters(self):
        """Test signup with unicode characters in name"""
        data = self.valid_data.copy()
        data["first_name"] = "José"
        data["last_name"] = "García"
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user: User = User.objects.get(phone_number=self.valid_data["phone_number"])
        self.assertEqual(user.first_name, "José")
        self.assertEqual(user.last_name, "García")

    def test_signup_phone_already_verified_but_used(self):
        """Test phone verified but already used by another user"""
        User.objects.create_user(
            phone_number="09123456788",
            first_name="Existing",
            last_name="User",
            gender=User.Gender.MALE,
        )

        cache.set("signup_verified_09123456788", {"phone_number": "09123456788"}, 600)
        data = self.valid_data.copy()
        data["phone_number"] = "09123456788"

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], SignUpError.PHONE_NUMBER_REUSE[0])  # type: ignore

    # ========== SELF-REFERRAL PREVENTION ==========
    def test_signup_self_referral_prevention(self):
        """Test that a user cannot refer themselves even if referral code matches"""
        # Mock the create_user to return a user with a predictable referral code
        original_create_user = User.objects.create_user

        created_user = None

        def mock_create_user(**kwargs):
            nonlocal created_user
            user = original_create_user(**kwargs)
            # Force a specific referral code
            user.referral_code = "ABCDEF"
            user.save(update_fields=["referral_code"])
            created_user = user
            return user

        try:
            User.objects.create_user = mock_create_user  # type: ignore

            data = self.valid_data.copy()
            data["referral"] = "ABCDEF"  # Same as the user's own code after creation

            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data["error_code"], SignUpError.REFERRAL_CODE_NOT_VALID[0])  # type: ignore

            from users_referrals.models import Referral

            self.assertFalse(
                Referral.objects.filter(referred_user=created_user).exists()
            )

        finally:
            User.objects.create_user = original_create_user  # type: ignore


class PhoneChangeFlowTest(TestCase):
    """Test phone change flow (4 steps)"""

    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()
        cache.clear()

        self.sms_patcher = patch("core.sms_task.send_sms_verification_task.delay")
        self.mock_sms = self.sms_patcher.start()
        self.mock_sms.return_value = None

        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )
        self.client.force_authenticate(user=self.user)

        self.old_request_url = reverse("users:phone-change-old-request")
        self.old_verify_url = reverse("users:phone-change-old-verify")
        self.new_request_url = reverse("users:phone-change-new-request")
        self.new_verify_url = reverse("users:phone-change-new-verify")

    def tearDown(self):
        self.sms_patcher.stop()
        cache.clear()

    # ========== SUCCESS FLOW ==========
    def test_complete_phone_change_flow(self):
        """Test complete phone change flow with all steps"""
        new_phone = "09123456711"

        response = self.client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cache_key = f"{OTP_CACHE_PREFIX}_{self.user.phone_number}"
        self.assertIsNotNone(cache.get(cache_key))

        state_key = f"phone_change_step_{self.user.id}"
        state = cache.get(state_key)
        self.assertIsNotNone(state)
        self.assertEqual(state["step"], "old_otp_sent")
        self.assertEqual(state["user_id"], self.user.id)

        response = self.client.post(self.old_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(cache.get(cache_key))

        state = cache.get(state_key)
        self.assertIsNotNone(state)
        self.assertEqual(state["step"], "old_verified")

        response = self.client.post(self.new_request_url, {"phone_number": new_phone})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        new_cache_key = f"{OTP_CACHE_PREFIX}_{new_phone}"
        self.assertIsNotNone(cache.get(new_cache_key))

        state = cache.get(state_key)
        self.assertIsNotNone(state)
        self.assertEqual(state["step"], "new_otp_sent")
        self.assertEqual(state["new_phone"], new_phone)

        response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user", response.data)  # type: ignore
        self.assertEqual(response.data["user"]["phone_number"], new_phone)  # type: ignore

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, new_phone)

        self.assertIsNone(cache.get(state_key))
        self.assertIsNone(cache.get(new_cache_key))

    def test_phone_change_flow_old_otp_expiry(self):
        """Test OTP expiry during phone change flow"""
        self.client.post(self.old_request_url)

        state_key = f"phone_change_step_{self.user.id}"
        cache.set(state_key, {"step": "old_otp_sent", "user_id": self.user.id}, -1)

        response = self.client.post(self.old_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], "OTP-002")  # type: ignore

    # ========== ERROR CASES - OLD PHONE ==========
    def test_old_otp_verify_without_state(self):
        """Test verifying old OTP without any state"""
        response = self.client.post(self.old_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], "OTP-002")  # type: ignore

    def test_old_otp_verify_invalid_otp(self):
        """Test verifying old OTP with invalid code"""
        self.client.post(self.old_request_url)

        response = self.client.post(self.old_verify_url, {"otp": "999999"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "OTP-003")  # type: ignore

        state = cache.get(f"phone_change_step_{self.user.id}")
        self.assertEqual(state["step"], "old_otp_sent")

    def test_old_otp_verify_wrong_step(self):
        """Test verifying old OTP at wrong step"""
        state_key = f"phone_change_step_{self.user.id}"
        cache.set(state_key, {"step": "old_verified", "user_id": self.user.id})

        response = self.client.post(self.old_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "OTP-004")  # type: ignore

    def test_old_otp_request_missing_otp(self):
        """Test old OTP verification without OTP code"""
        self.client.post(self.old_request_url)

        response = self.client.post(self.old_verify_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "OTP-001")  # type: ignore

    # ========== ERROR CASES - NEW PHONE ==========
    def test_new_otp_request_without_old_verification(self):
        """Test requesting new phone OTP without old verification"""
        response = self.client.post(
            self.new_request_url, {"phone_number": "09123456788"}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], "OTP-002")  # type: ignore

    def test_new_otp_request_missing_phone(self):
        """Test new phone OTP request without phone number"""
        self.client.post(self.old_request_url)
        self.client.post(self.old_verify_url, {"otp": "123456"})

        response = self.client.post(self.new_request_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "OTP-001")  # type: ignore

    def test_new_otp_request_duplicate_phone(self):
        """Test changing to a phone that already exists"""
        User.objects.create_user(
            phone_number="09123456788",
            first_name="Existing",
            last_name="User",
            gender=User.Gender.MALE,
        )

        self.client.post(self.old_request_url)
        self.client.post(self.old_verify_url, {"otp": "123456"})

        response = self.client.post(
            self.new_request_url, {"phone_number": "09123456788"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], SignUpError.PHONE_NUMBER_REUSE[0])  # type: ignore

    def test_new_otp_request_same_phone(self):
        """Test changing to the same phone number"""
        self.client.post(self.old_request_url)
        self.client.post(self.old_verify_url, {"otp": "123456"})

        response = self.client.post(
            self.new_request_url, {"phone_number": self.user.phone_number}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "USER-006")  # type: ignore

    def test_new_otp_verify_without_state(self):
        """Test verifying new phone OTP without state"""
        response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_new_otp_verify_invalid_otp(self):
        """Test verifying new phone OTP with invalid code"""
        self.client.post(self.old_request_url)
        self.client.post(self.old_verify_url, {"otp": "123456"})
        self.client.post(self.new_request_url, {"phone_number": "09123456788"})

        response = self.client.post(self.new_verify_url, {"otp": "999999"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "OTP-003")  # type: ignore

    def test_new_otp_verify_wrong_step(self):
        """Test verifying new OTP at wrong step"""
        state_key = f"phone_change_step_{self.user.id}"
        cache.set(state_key, {"step": "old_verified", "user_id": self.user.id})

        response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "OTP-004")  # type: ignore

    def test_new_otp_verify_missing_otp(self):
        """Test new OTP verification without OTP code"""
        self.client.post(self.old_request_url)
        self.client.post(self.old_verify_url, {"otp": "123456"})
        self.client.post(self.new_request_url, {"phone_number": "09123456788"})

        response = self.client.post(self.new_verify_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "OTP-001")  # type: ignore

    def test_new_otp_verify_expired_state(self):
        """Test verifying new phone with expired state"""
        self.client.post(self.old_request_url)
        self.client.post(self.old_verify_url, {"otp": "123456"})
        self.client.post(self.new_request_url, {"phone_number": "09123456788"})

        state_key = f"phone_change_step_{self.user.id}"
        cache.set(state_key, {"step": "new_otp_sent", "user_id": self.user.id}, -1)

        response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ========== RATE LIMITING TESTS ==========
    def test_throttle_phone_change_different_endpoints(self):
        """Test rate limiting with phone number"""
        for _ in range(5):
            response = self.client.post(
                self.new_request_url, {"phone_number": f"09123456711"}
            )
            self.assertNotEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            self.new_request_url, {"phone_number": "09123456711"}
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_throttle_phone_change(self):
        """Test rate limiting with ip endpoints"""
        # Make multiple requests to trigger throttle
        for _ in range(10):
            response = self.client.post(self.old_request_url)

        # After 10 requests, should be throttled
        # Note: Adjust based on your throttle settings
        response = self.client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    # ========== AUTHENTICATION TESTS ==========
    def test_phone_change_unauthenticated(self):
        """Test phone change endpoints without authentication"""
        client = APIClient()

        response = client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # type: ignore
        self.assertEqual(response.data["error_code"], AuthenticationError.TOKEN_NOT_PROVIDE[0])  # type: ignore

    def test_phone_change_inactive_user(self):
        """Test phone change for inactive user"""
        self.user.is_active = False
        self.user.save()

        response = self.client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class UserProfileViewTest(TestCase):
    """Test user profile view"""

    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
            date_of_birth=date(1990, 1, 1),
        )
        self.url = reverse("users:dashboard")
        self.client.force_authenticate(user=self.user)

    # ========== GET TESTS ==========
    def test_get_profile_success(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user", response.data)  # type: ignore
        user_data = response.data["user"]  # type: ignore
        self.assertEqual(user_data["phone_number"], "09123456789")
        self.assertEqual(user_data["first_name"], "John")
        self.assertEqual(user_data["last_name"], "Doe")
        self.assertEqual(user_data["gender"], User.Gender.MALE)
        self.assertEqual(user_data["date_of_birth"], "1990-01-01")
        self.assertIn("referral_code", user_data)

    def test_get_profile_unauthenticated(self):
        client = APIClient()
        response = client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # type: ignore
        self.assertEqual(response.data["error_code"], AuthenticationError.TOKEN_NOT_PROVIDE[0])  # type: ignore

    def test_get_profile_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ========== UPDATE (PUT) TESTS ==========
    def test_update_profile_success(self):
        data = {
            "first_name": "Jane",
            "last_name": "Smith",
            "gender": User.Gender.FEMALE,
            "date_of_birth": date(1995, 5, 5),
        }
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_data = response.data["user"]  # type: ignore
        self.assertEqual(user_data["first_name"], "Jane")
        self.assertEqual(user_data["last_name"], "Smith")
        self.assertEqual(user_data["gender"], User.Gender.FEMALE)
        self.assertEqual(user_data["date_of_birth"], "1995-05-05")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.last_name, "Smith")
        self.assertEqual(self.user.gender, User.Gender.FEMALE)
        self.assertEqual(self.user.date_of_birth, date(1995, 5, 5))

    def test_update_profile_partial(self):
        data = {"first_name": "Jane"}
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.last_name, "Doe")
        self.assertEqual(self.user.gender, User.Gender.MALE)

    def test_update_profile_multiple_fields(self):
        data = {
            "first_name": "Jane",
            "last_name": "Smith",
        }
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.last_name, "Smith")

    def test_update_profile_phone_number_read_only(self):
        data = {"phone_number": "09999999999"}
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09123456789")

    # ========== VALIDATION (single representative) ==========
    def test_update_profile_invalid_first_name(self):
        data = {"first_name": "Jo"}
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "VAL-002")  # type: ignore

    # ========== AUTHENTICATION TESTS ==========
    def test_update_profile_unauthenticated(self):
        client = APIClient()
        data = {"first_name": "Jane"}
        response = client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # type: ignore
        self.assertEqual(response.data["error_code"], AuthenticationError.TOKEN_NOT_PROVIDE[0])  # type: ignore

    def test_update_profile_picture_with_invalid_file_type(self):
        """Test updating profile picture with invalid file type"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Create a dummy text file (not an image)
        invalid_file = SimpleUploadedFile(
            "profile.txt", b"This is a text file", content_type="text/plain"
        )

        data = {
            "profile_picture": invalid_file,
        }

        response = self.client.put(self.url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # The error is wrapped in a VALIDATION_ERROR response
        self.assertEqual(response.data["error_code"], "VALIDATION_ERROR")  # type: ignore
        self.assertIn("profile_picture", response.data["error_message"])  # type: ignore

    # ========== DATE OF BIRTH NULL HANDLING ==========
    def test_update_profile_date_of_birth_to_null(self):
        """Test explicitly setting date_of_birth to null"""
        data = {"date_of_birth": None}

        response = self.client.put(self.url, data, format="json")

        # Your API wraps validation errors
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "VALIDATION_ERROR")  # type: ignore
        self.assertIn("date_of_birth", response.data["error_message"])  # type: ignore

    def test_update_profile_date_of_birth_to_empty_string(self):
        """Test sending empty string for date_of_birth"""
        data = {"date_of_birth": ""}

        response = self.client.put(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "VALIDATION_ERROR")  # type: ignore
        self.assertIn("date_of_birth", response.data["error_message"])  # type: ignore

    # ========== PROFILE PICTURE UPDATE ==========
    def test_update_profile_picture(self):
        # Create a valid image file
        image = Image.new("RGB", (100, 100), color="red")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="JPEG")
        image_bytes.seek(0)

        image_file = SimpleUploadedFile(
            "profile.jpg", image_bytes.read(), content_type="image/jpeg"
        )

        data = {
            "profile_picture": image_file,
        }

        response = self.client.put(self.url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify the profile picture was updated
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.profile_picture)
        # Should be saved as WebP
        self.assertTrue(self.user.profile_picture.name.endswith(".webp"))

        # Verify it's a valid WebP image
        img = Image.open(self.user.profile_picture)
        self.assertEqual(img.format, "WEBP")

    def test_update_profile_picture_with_png(self):

        # Create a PNG image
        image = Image.new("RGB", (100, 100), color="blue")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="PNG")
        image_bytes.seek(0)

        image_file = SimpleUploadedFile(
            "profile.png", image_bytes.read(), content_type="image/png"
        )

        data = {
            "profile_picture": image_file,
        }

        response = self.client.put(self.url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify the profile picture was converted to WebP
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.profile_picture)
        self.assertTrue(self.user.profile_picture.name.endswith(".webp"))

        img = Image.open(self.user.profile_picture)
        self.assertEqual(img.format, "WEBP")

    def test_update_profile_picture_with_webp(self):

        # Create a WEBP image
        image = Image.new("RGB", (100, 100), color="green")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="WEBP")
        image_bytes.seek(0)

        image_file = SimpleUploadedFile(
            "profile.webp", image_bytes.read(), content_type="image/webp"
        )

        data = {
            "profile_picture": image_file,
        }

        response = self.client.put(self.url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # WebP should remain WebP
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.profile_picture)
        self.assertTrue(self.user.profile_picture.name.endswith(".webp"))

        img = Image.open(self.user.profile_picture)
        self.assertEqual(img.format, "WEBP")
