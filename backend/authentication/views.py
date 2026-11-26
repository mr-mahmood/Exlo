from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from users.validators import validate_phone
from core.errors import APIError, OTPError, SessionError
from users.models import User
from users.serializers import UserProfileSerializer
from users_sessions.models import Session
from .token_services import create_tokens_for_user, refresh_tokens
from .authentication import RefreshTokenAuthentication
from .otp_service import OTPPurpose, generate_otp, verify_otp
from django.conf import settings
from .utils import make_cookie, create_signup_proof, SIGNUP_TTL, SIGNUP_PATH


class LoginRequestApiView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        phone_number = request.data.get("phone_number")
        phone_number = validate_phone(phone_number, skip_duplicate_check=True)

        if not phone_number:
            raise APIError(OTPError.PHONE_REQUIRED)

        # Generate and send OTP
        generate_otp(phone_number=phone_number, purpose=OTPPurpose.LOGIN)
        return Response(status=status.HTTP_200_OK)


class LoginVerifyApiView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = UserProfileSerializer

    def post(self, request):
        phone_number = request.data.get("phone_number")
        otp_code = request.data.get("otp")

        if phone_number is None or phone_number == "" or not otp_code:
            raise APIError(OTPError.PHONE_REQUIRED)

        phone_number = validate_phone(phone_number, skip_duplicate_check=True)

        # Verify OTP
        verify_otp(phone_number=phone_number, otp_code=otp_code, purpose=OTPPurpose.LOGIN)

        # no error raise by verify_otp so otp code is correct
        try:
            # Login flow
            user: User = User.objects.get(phone_number=phone_number)
            user.validate_account_status()
            user.update_last_login_at()

            session = Session.create_session(user, request)
            access, refresh = create_tokens_for_user(user, session)

            user = UserProfileSerializer(user, context={"request": request}).data

            response = Response({"user": user, "new_user": False}, status=status.HTTP_200_OK)

            make_cookie(response, {"access_token": access, "refresh_token": refresh})
            return response

        except User.DoesNotExist:
            signup_token = create_signup_proof(phone_number)
            response = Response({"user": None, "new_user": True}, status=status.HTTP_200_OK)
            make_cookie(response, {"signup_token": signup_token}, path=SIGNUP_PATH, max_age=SIGNUP_TTL)
            return response


class RefreshAPIView(APIView):
    authentication_classes = [RefreshTokenAuthentication]

    def post(self, request):

        refresh_token = request.auth

        try:
            new_access, new_refresh = refresh_tokens(refresh_token, request)
        except:
            raise APIError(SessionError.SESSION_EXPIRE)

        response = Response(status=status.HTTP_200_OK)

        make_cookie(response, {"access_token": new_access, "refresh_token": str(new_refresh)})

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

            except:
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
