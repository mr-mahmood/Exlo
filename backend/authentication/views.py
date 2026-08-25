from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from users.validators import validate_phone
from core.errors import APIError, AuthenticationError, OTPError, SessionError
from users.models import User
from users.serializers import UserProfileSerializer
from user_sessions.models import Session
from .token_services import create_tokens_for_user, refresh_tokens
from .utils import make_cookie
from .backends import RefreshTokenAuthentication
from .otp_service import generate_otp, verify_otp
from django.conf import settings
from django.core.cache import cache
from .throttles import OTPPhoneThrottle, OTPIPThrottle


class LoginRequestApiView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [OTPPhoneThrottle, OTPIPThrottle]

    def post(self, request):
        phone_number = request.data.get("phone_number")
        phone_number = validate_phone(phone_number, skip_duplicate_check=True)

        if not phone_number:
            raise APIError(OTPError.PHONE_REQUIRED)

        # Generate and send OTP
        result = generate_otp(phone_number)

        if result:
            return Response(status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)


class LoginVerifyApiView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = UserProfileSerializer
    throttle_classes = [OTPPhoneThrottle, OTPIPThrottle]

    def post(self, request):
        phone_number = request.data.get("phone_number")
        otp_code = request.data.get("otp")

        if not phone_number or not otp_code:
            raise APIError(OTPError.PHONE_REQUIRED)

        # Verify OTP
        verify_otp(phone_number, otp_code)

        # no error raise by verify_otp so otp code is correct
        try:
            # Login flow
            user: User = User.objects.get(phone_number=phone_number)
            user.validate_account_status()
            user.update_last_login_at()

            session = Session.create_session(user, request)
            tokens = create_tokens_for_user(user, session)

            response = Response(
                {
                    "user": UserProfileSerializer(
                        user, context={"request": request}
                    ).data,
                    "new_user": False,
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

        except User.DoesNotExist:
            # Signup flow
            cache_key = f"signup_verified_{phone_number}"
            cache.set(cache_key, {"phone_number": phone_number}, timeout=600)

            return Response(
                {
                    "user": None,
                    "new_user": True,
                },
                status=status.HTTP_200_OK,
            )


class RefreshAPIView(APIView):
    authentication_classes = [RefreshTokenAuthentication]

    def post(self, request):

        refresh_token = request.COOKIES.get("refresh_token")
        if not refresh_token:
            raise APIError(AuthenticationError.NO_REFRESH_TOKEN)

        try:
            new_access, new_refresh = refresh_tokens(refresh_token, request)
        except:
            raise APIError(SessionError.SESSION_EXPIRE)

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
                session: Session = Session.objects.get(session_id=session_id)
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
