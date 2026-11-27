# authentication/tests/test_views.py


from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from users.models import User
from users_sessions.models import Session
from django.conf import settings
from core.errors import (
    UserValidationError,
    SessionError,
    UserAccountError,
    OTPError,
)


class AuthenticationViewsTest(TestCase):
    """Test authentication views"""

    def setUp(self):
        self.client = APIClient()
        cache.clear()

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
        cache.clear()

    def test_login_request_success(self):
        """Test login request sends OTP"""
        data = {"phone_number": "09123456789"}
        response = self.client.post(self.login_request_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # OTP should be in cache
        cache_key = f"otp:login:-:09123456789"
        self.assertIsNotNone(cache.get(cache_key))

    @override_settings(OTP_MAX_ATTEMPTS=2)
    def test_decimal_scripts_share_cooldown_and_attempts(self):
        localized = "۰۹۱۲۳۴۵۶۷۸۹"
        response = self.client.post(self.login_request_url, {"phone_number": localized})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(self.login_request_url, {"phone_number": self.user.phone_number})
        self.assertEqual(response.json()["error_code"], OTPError.OTP_ALREADY_ACTIVE[0])
        for phone, error in ((self.user.phone_number, OTPError.OTP_INVALID), (localized, OTPError.OTP_ATTEMPTS_EXHAUSTED)):
            response = self.client.post(self.login_verify_url, {"phone_number": phone, "otp": "000000"})
            self.assertEqual(response.json()["error_code"], error[0])

    def test_login_endpoints_reject_non_string_phones(self):
        response = self.client.post(
            self.login_request_url,
            {"phone_number": self.user.phone_number},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        otp_key = f"otp:login:-:{self.user.phone_number}"
        original_otp = cache.get(otp_key)
        self.assertIsNotNone(original_otp)

        for url in (self.login_request_url, self.login_verify_url):
            for phone in (
                9123456789,
                0,
                1.5,
                True,
                False,
                [],
                ["09123456789"],
                {},
                {"phone": "09123456789"},
            ):
                with self.subTest(url=url, phone=phone):
                    response = self.client.post(url, {"phone_number": phone, "otp": "123456"}, format="json")
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    body = response.json()
                    self.assertFalse(body["success"])
                    self.assertIsNone(body["data"])
                    self.assertEqual(body["error_code"], UserValidationError.INVALID_PHONE_NUMBER[0])
                    for name in ("access_token", "refresh_token", "signup_token"):
                        self.assertNotIn(name, response.cookies)
                    self.assertEqual(cache.get(otp_key), original_otp)
                    self.assertIsNone(cache.get(f"signup_verified_{self.user.phone_number}"))
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(Session.objects.exists())

    def test_login_request_without_phone(self):
        """Test login request without phone number"""
        response = self.client.post(self.login_request_url, {})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:3000"])
    def test_duplicate_login_request_returns_retry_after(self):
        data = {"phone_number": self.user.phone_number}
        self.assertEqual(self.client.post(self.login_request_url, data).status_code, 200)

        response = self.client.post(self.login_request_url, data, HTTP_ORIGIN="http://localhost:3000")

        self.assert_otp_retry(response, OTPError.OTP_ALREADY_ACTIVE[0])
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:3000")
        self.assertIn("retry-after", response["Access-Control-Expose-Headers"].lower())

    def test_login_otp_locks_on_fifth_wrong_entry(self):
        data = {"phone_number": self.user.phone_number}
        self.assertEqual(self.client.post(self.login_request_url, data).status_code, 200)

        for _ in range(4):
            response = self.client.post(self.login_verify_url, {**data, "otp": "999999"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error_code"], OTPError.OTP_INVALID[0])

        response = self.client.post(self.login_verify_url, {**data, "otp": "999999"})
        self.assert_otp_retry(response, OTPError.OTP_ATTEMPTS_EXHAUSTED[0])
        response = self.client.post(self.login_verify_url, {**data, "otp": "123456"})
        self.assert_otp_retry(response, OTPError.OTP_ATTEMPTS_EXHAUSTED[0])
        self.assertFalse(Session.objects.exists())

    def assert_otp_retry(self, response, code):
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.json()["success"])
        self.assertIsNone(response.json()["data"])
        self.assertEqual(response.json()["error_code"], code)
        self.assertIn(int(response["Retry-After"]), range(1, 121))
        self.assertNotIn("retry_after", response.json())

    def test_login_request_null_phone(self):
        response = self.client.post(self.login_request_url, {"phone_number": None}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error_code"], UserValidationError.INVALID_PHONE_NUMBER[0])

    def test_login_verify_normalizes_phone(self):
        for phone, new_user in ((self.user.phone_number, False), ("09123456788", True)):
            with self.subTest(new_user=new_user):
                response = self.client.post(self.login_request_url, {"phone_number": phone}, format="json")
                self.assertEqual(response.status_code, status.HTTP_200_OK)

                response = self.client.post(
                    self.login_verify_url,
                    {"phone_number": f" {phone} ", "otp": "123456"},
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                body = response.json()
                self.assertTrue(body["success"])
                self.assertEqual(body["data"]["new_user"], new_user)
                if new_user:
                    self.assertIsNotNone(cache.get(f"signup_verified_{phone}"))
                    self.assertIsNone(cache.get(f"signup_verified_ {phone} "))
                    self.assertIn("signup_token", response.cookies)
                    self.assertNotIn("access_token", response.cookies)
                    self.assertNotIn("refresh_token", response.cookies)
                else:
                    self.assertEqual(body["data"]["user"]["phone_number"], phone)
                    self.assertEqual(Session.objects.filter(user=self.user).count(), 1)
                    self.assertIn("access_token", response.cookies)
                    self.assertIn("refresh_token", response.cookies)

    def test_login_verify_success_existing_user(self):
        """Test login verify with existing user"""
        # First request OTP
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})

        # Then verify
        data = {"phone_number": "09123456789", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_user"], False)
        self.assertEqual(response.data["user"]["phone_number"], "09123456789")

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
        self.assertEqual(response.data["new_user"], True)
        self.assertIsNone(response.data["user"])

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
        verify_response = self.client.post(self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"})

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
        verify_response = self.client.post(self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"})
        old_access_token = verify_response.cookies["access_token"].value
        old_refresh_token = verify_response.cookies["refresh_token"].value
        session = Session.objects.get(user=self.user)
        old_activity = session.last_activity_at
        self.user.refresh_from_db()
        old_login = self.user.last_login_at

        # Set cookies
        self.client.cookies = verify_response.cookies

        # Refresh
        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertNotEqual(response.cookies["access_token"].value, old_access_token)
        self.assertNotEqual(response.cookies["refresh_token"].value, old_refresh_token)
        self.assertEqual(response.json(), {"success": True, "data": None, "error_code": None})
        for name in ["access_token", "refresh_token"]:
            self.assertTrue(response.cookies[name]["httponly"])
            self.assertEqual(response.cookies[name]["path"], "/")
            self.assertEqual(bool(response.cookies[name]["secure"]), settings.SESSION_COOKIE_SECURE)
            self.assertEqual(response.cookies[name]["samesite"], settings.SESSION_COOKIE_SAMESITE)
            self.assertNotIn(response.cookies[name].value, response.content.decode())
        session.refresh_from_db()
        self.assertGreater(session.last_activity_at, old_activity)
        self.user.refresh_from_db()
        self.assertGreater(self.user.last_login_at, old_login)

    def test_refresh_without_token(self):
        """Test refresh without token"""
        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_request_new_user(self):
        """Test login request for non-existing user (should still work)"""
        data = {"phone_number": "09123456788"}  # Non-existent user
        response = self.client.post(self.login_request_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cache_key = f"otp:login:-:09123456788"
        self.assertIsNotNone(cache.get(cache_key))

    def test_login_request_with_whitespace_phone(self):
        """Test login request with phone number containing whitespace"""
        data = {"phone_number": " 09123456789 "}
        response = self.client.post(self.login_request_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # OTP should be stored with stripped phone number
        cache_key = f"otp:login:-:09123456789"
        self.assertIsNotNone(cache.get(cache_key))

    def test_login_request_with_whitespace_invalid_phone(self):
        """Test login request with phone number containing whitespace"""
        data = {"phone_number": "09 1234 56789"}
        response = self.client.post(self.login_request_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], UserValidationError.INVALID_PHONE_NUMBER[0])

    # --- LOGIN VERIFY TESTS ---

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
        self.assertEqual(response.data["error_code"], UserAccountError.USER_ACCOUNT_INACTIVE[0])

    def test_login_verify_missing_otp(self):
        """Test login verify with missing OTP"""
        data = {"phone_number": "09123456789"}  # Missing otp
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], OTPError.PHONE_REQUIRED[0])

    def test_login_verify_missing_phone(self):
        """Test login verify with missing phone number"""
        for data in (
            {"otp": "123456"},
            {"phone_number": None, "otp": "123456"},
            {"phone_number": "", "otp": "123456"},
        ):
            with self.subTest(data=data):
                response = self.client.post(self.login_verify_url, data, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data["error_code"], OTPError.PHONE_REQUIRED[0])

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
        self.assertEqual(set(response.json()["data"]), {"user", "new_user"})
        for name in ["access_token", "refresh_token"]:
            self.assertEqual(bool(response.cookies[name]["secure"]), settings.SESSION_COOKIE_SECURE)
            self.assertEqual(response.cookies[name]["samesite"], settings.SESSION_COOKIE_SAMESITE)
            self.assertNotIn(response.cookies[name].value, response.content.decode())

    def test_login_verify_new_user_sets_only_signup_cookie(self):
        """New users receive a signup proof cookie before account creation."""
        # Request OTP for new number
        self.client.post(self.login_request_url, {"phone_number": "09123456788"})

        data = {"phone_number": "09123456788", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_user"], True)

        self.assertNotIn("access_token", response.cookies)
        self.assertNotIn("refresh_token", response.cookies)
        self.assertIn("signup_token", response.cookies)
        self.assertTrue(response.cookies["signup_token"]["httponly"])
        self.assertEqual(response.json()["data"], {"user": None, "new_user": True})
        self.assertNotIn(response.cookies["signup_token"].value, response.content.decode())

    def test_login_verify_consumes_otp_and_preserves_cooldown(self):
        """Test that verification consumes the OTP and preserves its expiry."""
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        cache_key = f"otp:login:-:09123456789"
        deadline = cache.client.get_client().pexpiretime(cache.make_key(cache_key))

        data = {"phone_number": "09123456789", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(cache.client.get_client().pexpiretime(cache.make_key(cache_key)), deadline)
        replay = self.client.post(self.login_verify_url, data)
        self.assertEqual(replay.status_code, 404)
        self.assertEqual(replay.json()["error_code"], OTPError.OTP_NOT_FOUND[0])
        self.assertEqual(Session.objects.filter(user=self.user).count(), 1)
        duplicate = self.client.post(self.login_request_url, {"phone_number": data["phone_number"]})
        self.assert_otp_retry(duplicate, OTPError.OTP_ALREADY_ACTIVE[0])

    # --- REFRESH TESTS ---

    def test_refresh_with_invalid_token(self):
        """Test refresh with invalid token"""
        self.client.cookies["refresh_token"] = "invalid_token"

        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], SessionError.SESSION_EXPIRE[0])

    def test_refresh_inactive_user(self):
        """Test refresh for inactive user"""
        # Login to get tokens
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        verify_response = self.client.post(self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"})
        self.client.cookies = verify_response.cookies

        # Make user inactive
        self.user.is_active = False
        self.user.save()

        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], UserAccountError.USER_ACCOUNT_INACTIVE[0])

    def test_refresh_rotates_tokens(self):
        """Test that refresh rotates the token"""
        # Login to get tokens
        self.client.post(self.login_request_url, {"phone_number": "09123456789"})
        verify_response = self.client.post(self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"})
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
        verify_response = self.client.post(self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"})
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
        verify_response = self.client.post(self.login_verify_url, {"phone_number": "09123456789", "otp": "123456"})
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

    def test_repeated_login_requests_leave_original_otp_usable(self):
        data = {"phone_number": self.user.phone_number}
        response = self.client.post(self.login_request_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for _ in range(2):
            response = self.client.post(self.login_request_url, data)
            self.assert_otp_retry(response, OTPError.OTP_ALREADY_ACTIVE[0])

        response = self.client.post(self.login_verify_url, {**data, "otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_active_login_otp_is_independent_for_each_phone(self):
        for phone in ("09123456789", "09123456788", "09123456787"):
            with self.subTest(phone=phone):
                data = {"phone_number": phone}
                response = self.client.post(self.login_request_url, data)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

                response = self.client.post(self.login_request_url, data)
                self.assert_otp_retry(response, OTPError.OTP_ALREADY_ACTIVE[0])

    # --- EDGE CASES ---

    def test_login_verify_new_user_cache_set(self):
        """Test that cache is set for new user signup flow"""
        # Request OTP for new number
        self.client.post(self.login_request_url, {"phone_number": "09123456788"})

        data = {"phone_number": "09123456788", "otp": "123456"}
        response = self.client.post(self.login_verify_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_user"], True)

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
