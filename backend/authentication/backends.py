from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from core.errors import APIError, AuthSessionError, UserAccountError
from user_sessions.models import Session
from users.models import User


class AccessTokenAuthentication(JWTAuthentication):
    """
    Authenticate using access token from cookies.
    Validates both JWT and active session.
    """

    def authenticate(self, request):
        # 1. Extract access token from cookie
        access_token = request.COOKIES.get("access_token")
        if not access_token:
            raise APIError(AuthSessionError.COOKIES_NOT_PROVIDE)

        # 2. Validate JWT token
        try:
            validated_token = self.get_validated_token(access_token)
        except:
            raise APIError(AuthSessionError.INVALID_ACCESS_TOKEN)

        # 3. Get user from token
        try:
            user: User = self.get_user(validated_token)
            user.validate_account_status()
        except:
            raise APIError(UserAccountError.USER_NOT_EXIST)

        # 4. Validate active session
        session_id = validated_token.get("key_2")
        if not session_id:
            raise APIError(AuthSessionError.SESSION_NOT_FOUND)

        try:
            session: Session = Session.objects.get(
                session_id=session_id,
                user=user,
            )
        except Session.DoesNotExist:
            raise APIError(AuthSessionError.SESSION_INACTIVE)

        return (user, validated_token)


class RefreshTokenAuthentication(JWTAuthentication):
    """
    Authenticate using refresh token from cookies.
    Used exclusively for token refresh endpoint.
    """

    def authenticate(self, request):
        # 1. Extract refresh token from cookie
        refresh_token = request.COOKIES.get("refresh_token")
        if not refresh_token:
            raise APIError(AuthSessionError.COOKIES_NOT_PROVIDE)

        # 2. Validate refresh token
        try:
            refresh = RefreshToken(refresh_token)
        except TokenError as e:
            raise APIError(AuthSessionError.SESSION_EXPIRE)

        # 3. Get user from refresh token
        try:
            user: User = User.objects.get(id=refresh["key_1"])
            user.validate_account_status()
        except User.DoesNotExist:
            raise APIError(UserAccountError.USER_NOT_EXIST)

        # 4. Validate active session
        session_id = refresh.get("key_2")
        if not session_id:
            raise APIError(AuthSessionError.SESSION_NOT_FOUND)

        try:
            session: Session = Session.objects.get(
                session_id=session_id,
                user=user,
            )
        except Session.DoesNotExist:
            raise APIError(AuthSessionError.SESSION_INACTIVE)

        # 5. update session and user fildes
        # only update when new access token is requested
        session.update_last_activity_at()
        user.update_last_login_at()

        # 6. Return user with new access token
        access_token = refresh.access_token
        return (user, access_token)
