# authentication/tests/test_views.py
from django.test import TestCase
from django.urls import reverse
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from users.models import User
from user_sessions.models import Session
from django.conf import settings
from core.errors import (
    UserValidationError,
    AuthSessionError,
    UserAccountError,
    AuthOTPError,
)
from unittest.mock import patch


class AuthenticationViewsTest(TestCase):
    """Test authentication views"""

    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()
        cache.clear()

        # Mock the SMS task to prevent Celery connection
        self.sms_patcher = patch("core.sms_task.send_sms_verification_task.delay")
        self.mock_sms = self.sms_patcher.start()
        self.mock_sms.return_value = None

        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )

        self.login_request_url = reverse("authentication:login-request")
        self.login_verify_url = reverse("authentication:login-verify")
        self.logout_url = reverse("authentication:logout")
        self.refresh_url = reverse("authentication:refresh")

    def tearDown(self):
        self.sms_patcher.stop()
        cache.clear()

    def test_login_request_success(self):
        """Test login request sends OTP"""
        data = {"phone_number": "09123456789"}
        response = self.client.post(self.login_request_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # OTP should be in cache
        cache_key = f"otp_09123456789"
        self.assertIsNotNone(cache.get(cache_key))

    def test_login_request_without_phone(self):
        """Test login request without phone number"""
        response = self.client.post(self.login_request_url, {})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_verify_success_existing_user(self):
        """Test login verify with existing user"""
        # First request OTP
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})

        # Then verify
        data = {"phone_number": "09123456789", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_user"], False)  # type: ignore
        self.assertEqual(response.data["user"]["phone_number"], "09123456789")  # type: ignore

        # Check cookies set
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)

        # Check session created
        self.assertTrue(Session.objects.filter(user=self.user).exists())

    def test_login_verify_success_new_user(self):
        """Test login verify with new user"""
        # First request OTP for new number
        self.client.post(self.login_request_url, {"phone_number": "09123456788"})

        # Then verify
        data = {"phone_number": "09123456788", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_user"], True)  # type: ignore
        self.assertIsNone(response.data["user"])  # type: ignore

        # Check cache for signup
        cache_key = f"signup_verified_09123456788"
        self.assertIsNotNone(cache.get(cache_key))

    def test_login_verify_wrong_otp(self):
        """Test login verify with wrong OTP"""
        # Request OTP
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})

        # Wrong OTP
        data = {"phone_number": "09123456789", "otp": "999999"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_verify_expired_otp(self):
        """Test login verify with expired OTP"""
        # Don't request OTP, just verify
        data = {"phone_number": "09123456789", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_logout_success(self):
        """Test logout success"""
        # First login to get tokens
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        verify_response = self.client.post(
            self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"}
        )

        # Set cookies
        self.client.cookies = verify_response.cookies

        # Logout
        response = self.client.post(self.logout_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check cookies deleted
        self.assertEqual(response.cookies["access_token"].value, "")
        self.assertEqual(response.cookies["refresh_token"].value, "")

    def test_logout_without_session(self):
        """Test logout without active session"""
        response = self.client.post(self.logout_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_refresh_token_success(self):
        """Test refreshing tokens"""
        # Login to get tokens
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        verify_response = self.client.post(
            self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"}
        )
        old_access_token = verify_response.cookies["access_token"].value
        old_refresh_token = verify_response.cookies["refresh_token"].value

        # Set cookies
        self.client.cookies = verify_response.cookies

        # Refresh
        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertNotEqual(response.cookies["access_token"].value, old_access_token)
        self.assertNotEqual(response.cookies["refresh_token"].value, old_refresh_token)

    def test_refresh_without_token(self):
        """Test refresh without token"""
        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_request_new_user(self):
        """Test login request for non-existing user (should still work)"""
        data = {"phone_number": "09123456788"}  # Non-existent user
        response = self.client.post(self.login_request_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cache_key = f"otp_09123456788"
        self.assertIsNotNone(cache.get(cache_key))

    def test_login_request_with_whitespace_phone(self):
        """Test login request with phone number containing whitespace"""
        data = {"phone_number": " 09123456789 "}
        response = self.client.post(self.login_request_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # OTP should be stored with stripped phone number
        cache_key = f"otp_09123456789"
        self.assertIsNotNone(cache.get(cache_key))

    def test_login_request_with_whitespace_invalid_phone(self):
        """Test login request with phone number containing whitespace"""
        data = {"phone_number": "09 1234 56789"}
        response = self.client.post(self.login_request_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], UserValidationError.INVALID_PHONE_NUMBER[0])  # type: ignore

    # --- LOGIN VERIFY TESTS ---

    def test_login_verify_blocked_user(self):
        """Test login verify for blocked user"""
        self.user.block()

        # Request OTP
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})

        # Try to verify
        data = {"phone_number": "09123456789", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], UserAccountError.USER_ACCOUNT_BLOCKED[0])  # type: ignore

    def test_login_verify_inactive_user(self):
        """Test login verify for inactive user"""
        self.user.is_active = False
        self.user.save()

        # Request OTP
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})

        # Try to verify
        data = {"phone_number": "09123456789", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], UserAccountError.USER_ACCOUNT_INACTIVE[0])  # type: ignore

    def test_login_verify_missing_otp(self):
        """Test login verify with missing OTP"""
        data = {"phone_number": "09123456789"}  # Missing otp
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], AuthOTPError.PHONE_REQUIRED[0])  # type: ignore

    def test_login_verify_missing_phone(self):
        """Test login verify with missing phone number"""
        data = {"otp": "123456"}  # Missing phone_number
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], AuthOTPError.PHONE_REQUIRED[0])  # type: ignore

    def test_login_verify_existing_user_sets_cookies(self):
        """Test that login verify sets proper cookies for existing user"""
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        data = {"phone_number": "09123456789", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check cookies
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertTrue(response.cookies["access_token"]["httponly"])
        self.assertTrue(response.cookies["refresh_token"]["httponly"])
        self.assertEqual(response.cookies["access_token"]["path"], "/")
        self.assertEqual(response.cookies["refresh_token"]["path"], "/")

    def test_login_verify_new_user_no_cookies(self):
        """Test that login verify for new user does NOT set cookies"""
        # Request OTP for new number
        self.client.post(self.login_request_url, {"phone_number": "09123456788"})

        data = {"phone_number": "09123456788", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_user"], True)  # type: ignore

        # Should NOT have cookies (user not created yet)
        self.assertNotIn("access_token", response.cookies)
        self.assertNotIn("refresh_token", response.cookies)

    def test_login_verify_clears_otp_cache(self):
        """Test that OTP cache is cleared after successful verification"""
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        cache_key = f"otp_09123456789"
        self.assertIsNotNone(cache.get(cache_key))

        data = {"phone_number": "09123456789", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(cache.get(cache_key))

    # --- REFRESH TESTS ---

    def test_refresh_with_invalid_token(self):
        """Test refresh with invalid token"""
        self.client.cookies["refresh_token"] = "invalid_token"

        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], AuthSessionError.SESSION_EXPIRE[0])  # type: ignore

    def test_refresh_blocked_user(self):
        """Test refresh for blocked user"""
        # Login to get tokens
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        verify_response = self.client.post(
            self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"}
        )
        self.client.cookies = verify_response.cookies

        # Block user
        self.user.block()

        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], UserAccountError.USER_ACCOUNT_BLOCKED[0])  # type: ignore

    def test_refresh_inactive_user(self):
        """Test refresh for inactive user"""
        # Login to get tokens
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        verify_response = self.client.post(
            self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"}
        )
        self.client.cookies = verify_response.cookies

        # Make user inactive
        self.user.is_active = False
        self.user.save()

        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], UserAccountError.USER_ACCOUNT_INACTIVE[0])  # type: ignore

    def test_refresh_rotates_tokens(self):
        """Test that refresh rotates the token"""
        # Login to get tokens
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        verify_response = self.client.post(
            self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"}
        )
        self.client.cookies = verify_response.cookies

        old_access = verify_response.cookies["access_token"].value
        old_refresh = verify_response.cookies["refresh_token"].value

        # Refresh
        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.cookies["access_token"].value, old_access)
        self.assertNotEqual(response.cookies["refresh_token"].value, old_refresh)

    # --- LOGOUT TESTS ---

    def test_logout_deletes_session(self):
        """Test logout deletes the session from database"""
        # Login to create session
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        verify_response = self.client.post(
            self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"}
        )
        self.client.cookies = verify_response.cookies

        # Get session count before logout
        session_count = Session.objects.count()
        self.assertEqual(session_count, 1)

        # Logout
        response = self.client.post(self.logout_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Session should be deleted
        self.assertEqual(Session.objects.count(), 0)

    def test_logout_clears_cookies(self):
        """Test logout clears cookies"""
        # Login to get cookies
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        verify_response = self.client.post(
            self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"}
        )
        self.client.cookies = verify_response.cookies

        # Logout
        response = self.client.post(self.logout_url)

        # Check cookies deleted (empty values)
        self.assertEqual(response.cookies["access_token"].value, "")
        self.assertEqual(response.cookies["refresh_token"].value, "")

    def test_logout_with_invalid_refresh_token(self):
        """Test logout with invalid refresh token (should still clear cookies)"""
        self.client.cookies["refresh_token"] = "invalid_token"

        response = self.client.post(self.logout_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.cookies["access_token"].value, "")
        self.assertEqual(response.cookies["refresh_token"].value, "")

    # --- THROTTLE TESTS ---

    def test_login_request_throttle_phone(self):
        """Test rate limiting by phone number"""
        phone = "09123456789"
        phone_limit = 5  # Default OTPPhoneThrottle rate

        # Make requests up to the phone limit
        for _ in range(phone_limit):
            response = self.client.post(self.login_request_url, {"phone_number": phone})
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Next request should be throttled by phone
        response = self.client.post(self.login_request_url, {"phone_number": phone})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_login_request_throttle_different_phones(self):
        phones = ["09123456789", "09123456788", "09123456787"]
        phone_limit = 5

        for idx, phone in enumerate(phones):
            # Use a separate client with custom HTTP headers
            client = APIClient()
            # Set IP via META in the request method
            client.extra = {"REMOTE_ADDR": f"192.168.1.{idx + 10}"}

            for _ in range(phone_limit):
                response = client.post(
                    self.login_request_url,
                    {"phone_number": phone},
                    REMOTE_ADDR=f"192.168.1.{idx + 10}",
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)  # type: ignore

            response = client.post(
                self.login_request_url,
                {"phone_number": phone},
                REMOTE_ADDR=f"192.168.1.{idx + 10}",
            )
            self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)  # type: ignore

    def test_login_request_throttle_ip(self):
        """Test rate limiting by IP address"""
        phone = "09123456789"
        ip_limit = 10

        # Make requests up to the IP limit
        for i in range(ip_limit):
            response = self.client.post(self.login_request_url, {"phone_number": phone})
            # After IP throttle limit, should be throttled
            if i >= ip_limit - 1:
                pass

        # Try with different phone but same IP
        response = self.client.post(
            self.login_request_url, {"phone_number": "09123456788"}
        )
        # Should be throttled because IP limit is reached
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_login_verify_throttle(self):
        """Test rate limiting on verify endpoint"""
        # First request OTP
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})

        limit = 5  # Default throttle rate

        # Make verify requests with wrong OTP
        for _ in range(limit - 1):
            data = {"phone_number": "09123456789", "otp": "999999"}
            response = self.client.post(self.login_verify_url, data)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Next request should be throttled
        data = {"phone_number": "09123456789", "otp": "999999"}
        response = self.client.post(self.login_verify_url, data)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    # --- EDGE CASES ---

    def test_login_verify_new_user_cache_set(self):
        """Test that cache is set for new user signup flow"""
        # Request OTP for new number
        self.client.post(self.login_request_url, {"phone_number": "09123456788"})

        data = {"phone_number": "09123456788", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_user"], True)  # type: ignore

        # Check cache for signup
        cache_key = f"signup_verified_09123456788"
        self.assertIsNotNone(cache.get(cache_key))

    def test_login_verify_user_exists_creates_session(self):
        """Test that session is created for existing user"""
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        data = {"phone_number": "09123456789", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Session should be created
        self.assertTrue(Session.objects.filter(user=self.user).exists())
        session = Session.objects.get(user=self.user)
        self.assertEqual(session.ip_address, "127.0.0.1")
        self.assertIsNotNone(session.session_id)

    def test_login_verify_updates_last_login(self):
        """Test that last_login_at is updated on login"""
        self.assertIsNone(self.user.last_login_at)

        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        data = {"phone_number": "09123456789", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login_at)
