# authentication/tests/test_backends.py
# type: ignore

from django.test import TestCase
from django.test.client import RequestFactory
from rest_framework_simplejwt.tokens import RefreshToken
from authentication.token_services import create_tokens_for_user
from users.models import User
from user_sessions.models import Session
from authentication.backends import (
    AccessTokenAuthentication,
    RefreshTokenAuthentication,
)
from core.errors import APIError, AuthenticationError, UserAccountError, SessionError
from django.conf import settings
from datetime import timedelta


class AccessTokenAuthenticationTest(TestCase):
    """Test AccessTokenAuthentication"""

    def setUp(self):
        settings.DEBUG = True
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )

        # Create session
        self.request = self.factory.get("/")
        self.request.META["REMOTE_ADDR"] = "127.0.0.1"
        self.request.META["HTTP_USER_AGENT"] = "Test Agent"
        self.session = Session.create_session(self.user, self.request)

        # Create tokens
        refresh = RefreshToken.for_user(self.user)
        refresh["key_2"] = str(self.session.session_id)
        self.access_token = str(refresh.access_token)
        self.refresh_token = str(refresh)

    def tearDown(self):
        # Clean up sessions
        Session.objects.all().delete()

    # ========== SUCCESS CASES ==========
    def test_authenticate_success(self):
        """Test successful authentication with valid access token"""
        request = self.factory.get("/")
        request.COOKIES = {"access_token": self.access_token}

        auth = AccessTokenAuthentication()
        result = auth.authenticate(request)  # type: ignore

        # Check result is not None before unpacking
        self.assertIsNotNone(result)
        user, token = result

        self.assertEqual(user, self.user)
        self.assertIsNotNone(token)
        self.assertEqual(token, self.access_token)

    def test_authenticate_without_session_claim(self):
        """Test authentication with access token that doesn't have session_id claim"""
        # Create token without key_2
        refresh = RefreshToken.for_user(self.user)
        # Don't set key_2
        token = str(refresh.access_token)

        request = self.factory.get("/")
        request.COOKIES = {"access_token": token}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, SessionError.SESSION_NOT_FOUND[0]
        )

    # ========== ERROR CASES ==========

    def test_authenticate_no_cookie(self):
        """Test authentication without access token cookie"""
        request = self.factory.get("/")
        request.COOKIES = {}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, AuthenticationError.TOKEN_NOT_PROVIDE[0]
        )

    def test_authenticate_empty_cookie(self):
        """Test authentication with empty access token cookie"""
        request = self.factory.get("/")
        request.COOKIES = {"access_token": ""}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, AuthenticationError.TOKEN_NOT_PROVIDE[0]
        )

    def test_authenticate_invalid_access_token(self):
        """Test authentication with invalid access token"""
        request = self.factory.get("/")
        request.COOKIES = {"access_token": "invalid_token_123"}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, AuthenticationError.INVALID_ACCESS_TOKEN[0]
        )

    def test_authenticate_expired_token(self):
        """Test authentication with expired access token"""
        # Create token with expired time
        refresh = RefreshToken.for_user(self.user)
        refresh["key_2"] = str(self.session.session_id)

        # Get the access token and manually set expiration in payload
        # Set to epoch time (already expired)
        access = refresh.access_token
        access.payload["exp"] = 1  # type: ignore

        expired_token = str(access)

        request = self.factory.get("/")
        request.COOKIES = {"access_token": expired_token}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, AuthenticationError.INVALID_ACCESS_TOKEN[0]
        )

    def test_authenticate_expired_session(self):
        """Test authentication with valid token but deleted session"""
        # Delete session
        self.session.delete()

        request = self.factory.get("/")
        request.COOKIES = {"access_token": self.access_token}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_blocked_user(self):
        """Test authentication for blocked user"""
        self.user.block()

        request = self.factory.get("/")
        request.COOKIES = {"access_token": self.access_token}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_ACCOUNT_BLOCKED[0]
        )

    def test_authenticate_inactive_user(self):
        """Test authentication for inactive user"""
        self.user.is_active = False
        self.user.save()

        request = self.factory.get("/")
        request.COOKIES = {"access_token": self.access_token}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_ACCOUNT_INACTIVE[0]
        )

    def test_authenticate_deleted_user(self):
        """Test authentication for deleted user"""
        access, refresh = create_tokens_for_user(self.user, self.session)
        self.user.delete()

        request = self.factory.get("/")
        request.COOKIES = {
            "access_token": access,
            "refresh_token": refresh,
        }

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_NOT_EXIST[0]
        )

    def test_authenticate_malformed_token(self):
        """Test authentication with malformed token"""
        request = self.factory.get("/")
        request.COOKIES = {"access_token": "header.payload"}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, AuthenticationError.INVALID_ACCESS_TOKEN[0]
        )

    def test_authenticate_session_mismatch(self):
        """Test authentication when token's session doesn't match user"""
        # Create another user and session
        other_user = User.objects.create_user(
            phone_number="09123456788",
            first_name="Other",
            last_name="User",
            gender=User.Gender.MALE,
        )
        request2 = self.factory.get("/")
        request2.META["REMOTE_ADDR"] = "127.0.0.2"
        request2.META["HTTP_USER_AGENT"] = "Other Agent"
        other_session = Session.create_session(other_user, request2)

        # Create token for other_user with other_session
        refresh = RefreshToken.for_user(other_user)
        refresh["key_2"] = str(other_session.session_id)
        token = str(refresh.access_token)

        # Try to authenticate with self.user (should work because token identifies user)
        request = self.factory.get("/")
        request.COOKIES = {"access_token": token}

        auth = AccessTokenAuthentication()
        user, _ = auth.authenticate(request)  # type: ignore
        self.assertEqual(user, other_user)

    # ========== EDGE CASES ==========

    def test_authenticate_with_extra_claims(self):
        """Test authentication with token containing extra claims"""
        refresh = RefreshToken.for_user(self.user)
        refresh["key_2"] = str(self.session.session_id)
        refresh["custom_claim"] = "test_value"
        token = str(refresh.access_token)

        request = self.factory.get("/")
        request.COOKIES = {"access_token": token}

        auth = AccessTokenAuthentication()
        user, _ = auth.authenticate(request)  # type: ignore

        self.assertEqual(user, self.user)

    def test_authenticate_case_sensitive_token(self):
        """Test that token is case sensitive"""
        # Modify token case
        modified_token = self.access_token.upper()

        request = self.factory.get("/")
        request.COOKIES = {"access_token": modified_token}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, AuthenticationError.INVALID_ACCESS_TOKEN[0]
        )


class RefreshTokenAuthenticationTest(TestCase):
    """Test RefreshTokenAuthentication"""

    def setUp(self):
        settings.DEBUG = True
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )

        # Create session
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"
        self.session = Session.create_session(self.user, request)

        # Create refresh token
        self.refresh = RefreshToken.for_user(self.user)
        self.refresh["key_2"] = str(self.session.session_id)
        self.refresh_token = str(self.refresh)

    def tearDown(self):
        # Clean up sessions
        Session.objects.all().delete()

    # ========== SUCCESS CASES ==========

    def test_authenticate_success(self):
        """Test successful refresh token authentication"""
        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": self.refresh_token}

        auth = RefreshTokenAuthentication()
        user, token = auth.authenticate(request)  # type: ignore

        self.assertEqual(user, self.user)
        self.assertIsNotNone(token)

    def test_authenticate_without_session_claim(self):
        """Test refresh authentication with token that doesn't have session_id claim"""
        refresh = RefreshToken.for_user(self.user)
        # Don't set key_2
        token = str(refresh)

        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": token}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, SessionError.SESSION_NOT_FOUND[0]
        )

    # ========== ERROR CASES ==========

    def test_authenticate_no_cookie(self):
        """Test authentication without refresh token cookie"""
        request = self.factory.get("/")
        request.COOKIES = {}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, AuthenticationError.TOKEN_NOT_PROVIDE[0]
        )

    def test_authenticate_empty_cookie(self):
        """Test authentication with empty refresh token cookie"""
        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": ""}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, AuthenticationError.TOKEN_NOT_PROVIDE[0]
        )

    def test_authenticate_invalid_refresh_token(self):
        """Test authentication with invalid refresh token"""
        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": "invalid_token_123"}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_expired_refresh_token(self):
        """Test authentication with expired refresh token"""
        # Create expired refresh token
        refresh = RefreshToken.for_user(self.user)
        refresh.set_exp(lifetime=timedelta(seconds=-3600))
        expired_token = str(refresh)

        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": expired_token}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_expired_session(self):
        """Test authentication with valid refresh token but deleted session"""
        self.session.delete()

        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": self.refresh_token}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_blocked_user(self):
        """Test authentication for blocked user"""
        self.user.block()

        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": self.refresh_token}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_ACCOUNT_BLOCKED[0]
        )

    def test_authenticate_inactive_user(self):
        """Test authentication for inactive user"""
        self.user.is_active = False
        self.user.save()

        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": self.refresh_token}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_ACCOUNT_INACTIVE[0]
        )

    def test_authenticate_deleted_user(self):
        """Test authentication for deleted user"""
        access, refresh = create_tokens_for_user(self.user, self.session)
        self.user.delete()

        request = self.factory.get("/")
        request.COOKIES = {
            "access_token": access,
            "refresh_token": refresh,
        }

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_NOT_EXIST[0]
        )

    def test_authenticate_malformed_token(self):
        """Test authentication with malformed refresh token"""
        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": "header.payload"}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_blacklisted_token(self):
        """Test authentication with blacklisted refresh token"""
        # Blacklist the token
        self.refresh.blacklist()

        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": self.refresh_token}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    # ========== EDGE CASES ==========

    def test_authenticate_with_extra_claims(self):
        """Test authentication with refresh token containing extra claims"""
        refresh = RefreshToken.for_user(self.user)
        refresh["key_2"] = str(self.session.session_id)
        refresh["custom_claim"] = "test_value"
        token = str(refresh)

        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": token}

        auth = RefreshTokenAuthentication()
        user, _ = auth.authenticate(request)  # type: ignore

        self.assertEqual(user, self.user)

    def test_authenticate_case_sensitive_token(self):
        """Test that refresh token is case sensitive"""
        modified_token = self.refresh_token.upper()

        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": modified_token}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)  # type: ignore

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_session_mismatch(self):
        """Test refresh authentication when token's session doesn't match user"""
        # Create another user and session
        other_user = User.objects.create_user(
            phone_number="09123456788",
            first_name="Other",
            last_name="User",
            gender=User.Gender.MALE,
        )
        request2 = self.factory.get("/")
        request2.META["REMOTE_ADDR"] = "127.0.0.2"
        request2.META["HTTP_USER_AGENT"] = "Other Agent"
        other_session = Session.create_session(other_user, request2)

        # Create refresh token for other_user with other_session
        refresh = RefreshToken.for_user(other_user)
        refresh["key_2"] = str(other_session.session_id)
        token = str(refresh)

        request = self.factory.get("/")
        request.COOKIES = {"refresh_token": token}

        auth = RefreshTokenAuthentication()
        user, _ = auth.authenticate(request)  # type: ignore
        self.assertEqual(user, other_user)


# ========== AUTH TRANSPORT HEADER TESTS ==========
class AccessTokenAuthenticationWithBearerTransportTest(TestCase):
    """Test AccessTokenAuthentication with X-Auth-Transport: bearer header"""

    def setUp(self):
        settings.DEBUG = True
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )

        # Create session
        self.request = self.factory.get("/")
        self.request.META["REMOTE_ADDR"] = "127.0.0.1"
        self.request.META["HTTP_USER_AGENT"] = "Test Agent"
        self.session = Session.create_session(self.user, self.request)

        # Create tokens
        refresh = RefreshToken.for_user(self.user)
        refresh["key_2"] = str(self.session.session_id)
        self.access_token = str(refresh.access_token)

    def tearDown(self):
        Session.objects.all().delete()

    # ========== SUCCESS CASES ==========

    def test_authenticate_with_bearer_header_instead_of_cookie(self):
        """Test successful authentication with access token in Authorization header when X-Auth-Transport: bearer is set"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.access_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = AccessTokenAuthentication()
        result = auth.authenticate(request)

        self.assertIsNotNone(result)
        user, token = result

        self.assertEqual(user, self.user)
        self.assertIsNotNone(token)
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        self.assertEqual(token, self.access_token)

    def test_authenticate_with_bearer_header_and_no_cookie(self):
        """Test authentication with Authorization header but no cookie when X-Auth-Transport: bearer is set"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.access_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"
        request.COOKIES = {}

        auth = AccessTokenAuthentication()
        result = auth.authenticate(request)

        self.assertIsNotNone(result)
        user, token = result
        self.assertEqual(user, self.user)
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        self.assertEqual(token, self.access_token)

    def test_authenticate_with_bearer_header_and_cookie_both_present(self):
        """Test authentication with both Authorization header and cookie when X-Auth-Transport: bearer is set"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.access_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"
        request.COOKIES = {"access_token": "cookie_token_123"}

        auth = AccessTokenAuthentication()
        result = auth.authenticate(request)

        # Should use Authorization header
        self.assertIsNotNone(result)
        user, token = result
        self.assertEqual(user, self.user)
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        self.assertEqual(token, self.access_token)

    # ========== ERROR CASES ==========
    def test_authenticate_without_auth_header_when_bearer_requested(self):
        """Test authentication fails when X-Auth-Transport: bearer is set but no Authorization header provided"""
        request = self.factory.get("/")
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"
        request.COOKIES = {}

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, AuthenticationError.TOKEN_NOT_PROVIDE[0]
        )

    def test_authenticate_with_bearer_header_and_invalid_token(self):
        """Test authentication fails with invalid token when X-Auth-Transport: bearer is set"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = "Bearer invalid_token_123"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, AuthenticationError.INVALID_ACCESS_TOKEN[0]
        )

    def test_authenticate_with_bearer_header_and_expired_token(self):
        """Test authentication fails with expired token when X-Auth-Transport: bearer is set"""
        refresh = RefreshToken.for_user(self.user)
        refresh["key_2"] = str(self.session.session_id)
        access = refresh.access_token
        access.payload["exp"] = 1
        expired_token = str(access)

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {expired_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, AuthenticationError.INVALID_ACCESS_TOKEN[0]
        )

    def test_authenticate_with_bearer_header_and_malformed_token(self):
        """Test authentication fails with malformed token when X-Auth-Transport: bearer is set"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = "Bearer header.payload"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, AuthenticationError.INVALID_ACCESS_TOKEN[0]
        )

    def test_authenticate_with_bearer_header_and_case_sensitive_token(self):
        """Test authentication fails with case modified token when X-Auth-Transport: bearer is set"""
        modified_token = self.access_token.upper()

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {modified_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, AuthenticationError.INVALID_ACCESS_TOKEN[0]
        )

    def test_authenticate_with_bearer_header_and_expired_session(self):
        """Test authentication with valid token but deleted session when X-Auth-Transport: bearer is set"""
        self.session.delete()

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.access_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_with_bearer_header_and_blocked_user(self):
        """Test authentication for blocked user when X-Auth-Transport: bearer is set"""
        self.user.block()

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.access_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_ACCOUNT_BLOCKED[0]
        )

    def test_authenticate_with_bearer_header_and_inactive_user(self):
        """Test authentication for inactive user when X-Auth-Transport: bearer is set"""
        self.user.is_active = False
        self.user.save()

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.access_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_ACCOUNT_INACTIVE[0]
        )

    def test_authenticate_with_bearer_header_and_deleted_user(self):
        """Test authentication for deleted user when X-Auth-Transport: bearer is set"""
        access, refresh = create_tokens_for_user(self.user, self.session)
        self.user.delete()

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {access}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = AccessTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_NOT_EXIST[0]
        )

    # ========== EDGE CASES ==========

    def test_authenticate_with_bearer_header_and_extra_claims(self):
        """Test authentication with token containing extra claims when X-Auth-Transport: bearer is set"""
        refresh = RefreshToken.for_user(self.user)
        refresh["key_2"] = str(self.session.session_id)
        refresh["custom_claim"] = "test_value"
        token = str(refresh.access_token)

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = AccessTokenAuthentication()
        user, _ = auth.authenticate(request)

        self.assertEqual(user, self.user)

    def test_authenticate_with_bearer_header_case_insensitive(self):
        """Test X-Auth-Transport header is case insensitive"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.access_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "BEARER"

        auth = AccessTokenAuthentication()
        result = auth.authenticate(request)

        self.assertIsNotNone(result)
        user, token = result
        self.assertEqual(user, self.user)


class RefreshTokenAuthenticationWithBearerTransportTest(TestCase):
    """Test RefreshTokenAuthentication with X-Auth-Transport: bearer header"""

    def setUp(self):
        settings.DEBUG = True
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )

        # Create session
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"
        self.session = Session.create_session(self.user, request)

        # Create refresh token
        self.refresh = RefreshToken.for_user(self.user)
        self.refresh["key_2"] = str(self.session.session_id)
        self.refresh_token = str(self.refresh)

    def tearDown(self):
        Session.objects.all().delete()

    # ========== SUCCESS CASES ==========

    def test_authenticate_with_bearer_header_instead_of_cookie(self):
        """Test successful refresh token authentication with X-Auth-Transport: bearer"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.refresh_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = RefreshTokenAuthentication()
        user, token = auth.authenticate(request)

        self.assertEqual(user, self.user)
        self.assertIsNotNone(token)

    def test_authenticate_with_bearer_header_and_no_cookie(self):
        """Test refresh authentication with Authorization header but no cookie when X-Auth-Transport: bearer is set"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.refresh_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"
        request.COOKIES = {}

        auth = RefreshTokenAuthentication()
        user, token = auth.authenticate(request)

        self.assertEqual(user, self.user)
        self.assertIsNotNone(token)

    def test_authenticate_with_bearer_header_and_cookie_both_present(self):
        """Test refresh authentication with both Authorization header and cookie when X-Auth-Transport: bearer is set"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.refresh_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"
        request.COOKIES = {"refresh_token": "cookie_token_123"}

        auth = RefreshTokenAuthentication()
        user, token = auth.authenticate(request)

        # Should use Authorization header
        self.assertEqual(user, self.user)
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        self.assertEqual(token, self.refresh_token)

    # ========== ERROR CASES ==========

    def test_authenticate_without_auth_header_when_bearer_requested(self):
        """Test refresh authentication fails when X-Auth-Transport: bearer is set but no Authorization header provided"""
        request = self.factory.get("/")
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"
        request.COOKIES = {}

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, AuthenticationError.TOKEN_NOT_PROVIDE[0]
        )

    def test_authenticate_with_bearer_header_and_invalid_token(self):
        """Test refresh authentication fails with invalid token when X-Auth-Transport: bearer is set"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = "Bearer invalid_token_123"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_with_bearer_header_and_expired_token(self):
        """Test refresh authentication fails with expired token when X-Auth-Transport: bearer is set"""
        refresh = RefreshToken.for_user(self.user)
        refresh.set_exp(lifetime=timedelta(seconds=-3600))
        expired_token = str(refresh)

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {expired_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_with_bearer_header_and_malformed_token(self):
        """Test refresh authentication fails with malformed token when X-Auth-Transport: bearer is set"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = "Bearer header.payload"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_with_bearer_header_and_blacklisted_token(self):
        """Test refresh authentication with blacklisted token when X-Auth-Transport: bearer is set"""
        self.refresh.blacklist()

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.refresh_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_with_bearer_header_and_expired_session(self):
        """Test refresh authentication with valid token but deleted session when X-Auth-Transport: bearer is set"""
        self.session.delete()

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.refresh_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(context.exception.error_code, SessionError.SESSION_EXPIRE[0])

    def test_authenticate_with_bearer_header_and_blocked_user(self):
        """Test refresh authentication for blocked user when X-Auth-Transport: bearer is set"""
        self.user.block()

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.refresh_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_ACCOUNT_BLOCKED[0]
        )

    def test_authenticate_with_bearer_header_and_inactive_user(self):
        """Test refresh authentication for inactive user when X-Auth-Transport: bearer is set"""
        self.user.is_active = False
        self.user.save()

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.refresh_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_ACCOUNT_INACTIVE[0]
        )

    def test_authenticate_with_bearer_header_and_deleted_user(self):
        """Test refresh authentication for deleted user when X-Auth-Transport: bearer is set"""
        access, refresh = create_tokens_for_user(self.user, self.session)
        self.user.delete()

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {refresh}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = RefreshTokenAuthentication()
        with self.assertRaises(APIError) as context:
            auth.authenticate(request)

        self.assertEqual(
            context.exception.error_code, UserAccountError.USER_NOT_EXIST[0]
        )

    # ========== EDGE CASES ==========

    def test_authenticate_with_bearer_header_and_extra_claims(self):
        """Test refresh authentication with token containing extra claims when X-Auth-Transport: bearer is set"""
        refresh = RefreshToken.for_user(self.user)
        refresh["key_2"] = str(self.session.session_id)
        refresh["custom_claim"] = "test_value"
        token = str(refresh)

        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "bearer"

        auth = RefreshTokenAuthentication()
        user, _ = auth.authenticate(request)

        self.assertEqual(user, self.user)

    def test_authenticate_with_bearer_header_case_insensitive(self):
        """Test X-Auth-Transport header is case insensitive for refresh"""
        request = self.factory.get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.refresh_token}"
        request.META["HTTP_X_AUTH_TRANSPORT"] = "BEARER"

        auth = RefreshTokenAuthentication()
        user, token = auth.authenticate(request)

        self.assertEqual(user, self.user)
        self.assertIsNotNone(token)


# ========== UTILITY FUNCTION TESTS ==========
class AuthTransportUtilsTest(TestCase):
    """Test auth transport utility functions"""

    def setUp(self):
        settings.DEBUG = True
        self.factory = RequestFactory()

    def test_is_bearer_transport_with_bearer_header(self):
        """Test is_bearer_transport returns True with bearer header"""
        request = self.factory.get("/")
        request.headers = {"X-Auth-Transport": "bearer"}

        from authentication.utils import is_bearer_transport

        self.assertTrue(is_bearer_transport(request))

    def test_is_bearer_transport_with_BEARER_header(self):
        """Test is_bearer_transport returns True with BEARER header (case insensitive)"""
        request = self.factory.get("/")
        request.headers = {"X-Auth-Transport": "BEARER"}

        from authentication.utils import is_bearer_transport

        self.assertTrue(is_bearer_transport(request))

    def test_is_bearer_transport_with_mixed_case_header(self):
        """Test is_bearer_transport returns True with mixed case header"""
        request = self.factory.get("/")
        request.headers = {"X-Auth-Transport": "BeArEr"}

        from authentication.utils import is_bearer_transport

        self.assertTrue(is_bearer_transport(request))

    def test_is_bearer_transport_without_header(self):
        """Test is_bearer_transport returns False without header"""
        request = self.factory.get("/")
        request.headers = {}

        from authentication.utils import is_bearer_transport

        self.assertFalse(is_bearer_transport(request))

    def test_is_bearer_transport_with_different_value(self):
        """Test is_bearer_transport returns False with different value"""
        request = self.factory.get("/")
        request.headers = {"X-Auth-Transport": "cookie"}

        from authentication.utils import is_bearer_transport

        self.assertFalse(is_bearer_transport(request))
