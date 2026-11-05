from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from core.errors import APIError, AuthenticationError, SessionError
from users_sessions.models import Session
from users.models import User


class AccessTokenAuthentication(JWTAuthentication):

    def get_user(self, validated_token):
        user_id = validated_token.get("key_1")
        if not user_id:
            raise APIError(AuthenticationError.INVALID_ACCESS_TOKEN)
        user = User.objects.get_user(user_id)
        return user

    def authenticate(self, request):

        access_token = request.COOKIES.get("access_token")

        if not access_token:
            raise APIError(AuthenticationError.TOKEN_NOT_PROVIDE)

        # 2. Validate JWT token
        try:
            validated_token = self.get_validated_token(access_token)
        except (TokenError, InvalidToken):
            raise APIError(AuthenticationError.INVALID_ACCESS_TOKEN)

        # 3. Get user from token
        user: User = self.get_user(validated_token)
        user.validate_account_status()

        # 4. Validate active session
        session_id = validated_token.get("key_2")
        if not session_id:
            raise APIError(SessionError.SESSION_NOT_FOUND)

        try:
            Session.objects.get(
                session_id=session_id,
                user=user,
            )
        except Session.DoesNotExist:
            raise APIError(SessionError.SESSION_EXPIRE)

        return (user, access_token)


class RefreshTokenAuthentication(JWTAuthentication):

    def get_user(self, validated_token):
        user_id = validated_token.get("key_1")
        if not user_id:
            raise APIError(AuthenticationError.INVALID_ACCESS_TOKEN)
        user = User.objects.get_user(user_id)
        return user

    def authenticate(self, request):

        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            raise APIError(AuthenticationError.TOKEN_NOT_PROVIDE)

        # 2. Validate refresh token
        try:
            refresh = RefreshToken(refresh_token)
        except TokenError as e:
            raise APIError(SessionError.SESSION_EXPIRE)

        # 3. Get user from token
        user: User = self.get_user(refresh)
        user.validate_account_status()

        # 4. Validate active session
        session_id = refresh.get("key_2")
        if not session_id:
            raise APIError(SessionError.SESSION_NOT_FOUND)

        try:
            session: Session = Session.objects.get(
                session_id=session_id,
                user=user,
            )
        except Session.DoesNotExist:
            raise APIError(SessionError.SESSION_EXPIRE)

        # 5. update session and user fields
        # only update when new access token is requested
        session.update_last_activity_at()
        user.update_last_login_at()

        return (user, refresh_token)
