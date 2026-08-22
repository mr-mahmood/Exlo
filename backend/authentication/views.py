from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from core.errors import APIError, AuthSessionError, AuthOTPError, UserAccountError
from users.models import User
from users.serializers import UserProfileSerializer
from sessions.models import UserSession
from .services import TokenService
from .backends import RefreshTokenAuthentication
from .otp_service import generate_otp, verify_otp
from .utils import make_cookie
from django.conf import settings


class RequestOTPApiView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        phone_number = request.data.get("phone_number")

        if not phone_number:
            raise APIError(AuthOTPError.OTP_PHONE_REQUIRED)

        # Check if user exists and is not blocked
        try:
            user: User = User.objects.get(phone_number=phone_number)
            user.validate_account_status(login=True)
        except User.DoesNotExist:
            raise APIError(UserAccountError.USER_NOT_EXIST)

        # Generate and send OTP
        result = generate_otp(phone_number)

        if result:
            return Response(status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)


class VerifyOTPApiView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        phone_number = request.data.get("phone_number")
        otp_code = request.data.get("otp")

        if not phone_number or not otp_code:
            raise APIError(AuthOTPError.OTP_PHONE_REQUIRED)

        # Verify OTP
        result = verify_otp(phone_number, otp_code)

        if result:
            user: User = User.objects.get(phone_number=phone_number)

            if not user.is_verified:
                user.verify()
            user.update_last_login_at()

            session = UserSession.create_session(user, request)
            tokens = TokenService.create_tokens_for_user(user, session)

            response = Response(
                {
                    "user": UserProfileSerializer(
                        user, context={"request": request}
                    ).data,
                },
                status=status.HTTP_200_OK,
            )

            make_cookie(
                response,
                {
                    "access_token": tokens["access"],
                    "refresh_token": tokens["refresh"],
                },
            )

            return response


class RefreshAPIView(APIView):
    authentication_classes = [RefreshTokenAuthentication]

    def post(self, request):

        refresh_token = request.COOKIES.get("refresh_token")
        if not refresh_token:
            raise APIError(AuthSessionError.NO_REFRESH_TOKEN)

        try:
            new_access, new_refresh = TokenService.refresh_tokens(
                refresh_token,
                request,
            )
        except:
            raise APIError(AuthSessionError.SESSION_EXPIRE)

        response = Response(status=status.HTTP_200_OK)

        make_cookie(
            response,
            {
                "access_token": new_access,
                "refresh_token": str(new_refresh),
            },
        )

        return response


class LogoutAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):

        refresh_token = request.COOKIES.get("refresh_token")
        if refresh_token:
            try:
                refresh = RefreshToken(refresh_token)
                refresh.blacklist()

                session_id = refresh.get("key_2")
                session = UserSession.objects.get(session_id=session_id)
                session.delete()

            except TokenError:
                pass  # Token already invalid or expired

        # Clear cookies
        response = Response(status=status.HTTP_200_OK)

        response.delete_cookie(
            "access_token",
            path="/",
            domain=settings.SESSION_COOKIE_DOMAIN,
        )
        response.delete_cookie(
            "refresh_token",
            path="/",
            domain=settings.SESSION_COOKIE_DOMAIN,
        )

        return response
