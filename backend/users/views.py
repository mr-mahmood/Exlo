from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from users.serializers import UserSignupSerializer, UserProfileSerializer
from users.models import User
from user_referrals.models import Referral
from user_sessions.models import Session
from authentication.otp_service import generate_otp, verify_otp
from authentication.token_services import create_tokens_for_user
from authentication.utils import attach_auth_tokens
from authentication.throttles import OTPPhoneThrottle, OTPIPThrottle
from core.errors import APIError, OTPError, SignUpError, UserAccountError
from users.validators import validate_phone
from typing import cast


class UserSignupAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = UserSignupSerializer

    def post(self, request):
        phone_number = request.data.get("phone_number")
        if not phone_number:
            raise APIError(OTPError.PHONE_REQUIRED)

        # Check if phone is verified
        verified_key = f"signup_verified_{phone_number}"
        verified_data = cache.get(verified_key)

        if not verified_data:
            raise APIError(SignUpError.SIGN_UP_NOT_ALLOWED)

        # Validate data
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        referral_code = request.data.get("referral")

        try:
            with transaction.atomic():
                # Create user
                user = cast(User, serializer.save())

                # Create referral if provided
                if referral_code:
                    if referral_code != user.referral_code:
                        referrer = User.objects.get(referral_code=referral_code)
                        Referral.objects.create(
                            referrer=referrer,
                            referred_user=user,
                            referred_at=timezone.now(),
                        )
                    else:
                        raise APIError(SignUpError.REFERRAL_CODE_NOT_VALID)

                # Create session and tokens
                session = Session.create_session(user, request)
                access, refresh = create_tokens_for_user(user, session)

                # Prepare response
                response = Response(
                    {
                        "user": self.serializer_class(
                            user,
                            context={"request": request},
                        ).data,
                    },
                    status=status.HTTP_201_CREATED,
                )

                attach_auth_tokens(
                    response,
                    request,
                    access,
                    refresh,
                )

                # Clean up cache
                cache.delete(verified_key)
                return response

        except IntegrityError:
            raise APIError(SignUpError.UNEXPECTED_ERROR)


class PhoneChangeOldRequestAPIView(APIView):
    throttle_classes = [OTPPhoneThrottle, OTPIPThrottle]

    def post(self, request):
        user: User = request.user
        user.validate_account_status()

        # Generate OTP for current phone
        result = generate_otp(user.phone_number)

        # Set state: step 1
        cache_key = f"phone_change_step_{user.id}"
        cache.set(
            cache_key,
            {
                "step": "old_otp_sent",
                "user_id": user.id,
            },
            timeout=300,
        )

        if result:
            return Response(status=status.HTTP_200_OK)
        else:
            raise APIError(OTPError.OLD_PHONE_OTP_FAILED)


class PhoneChangeOldVerifyAPIView(APIView):
    throttle_classes = [OTPPhoneThrottle, OTPIPThrottle]

    def post(self, request):
        user: User = request.user
        otp = request.data.get("otp")

        if not otp:
            raise APIError(OTPError.PHONE_REQUIRED)

        # Check state: must be at step 1
        cache_key = f"phone_change_step_{user.id}"
        state = cache.get(cache_key)

        if not state:
            raise APIError(OTPError.OTP_NOT_FOUND)

        if state.get("step") != "old_otp_sent":
            raise APIError(OTPError.INVALID_STEP)

        # Verify OTP
        verify_otp(user.phone_number, otp)

        # Update state: step 2
        cache.set(
            cache_key,
            {
                "step": "old_verified",
                "user_id": user.id,
            },
            timeout=300,
        )

        return Response(
            status=status.HTTP_200_OK,
        )


class PhoneChangeNewRequestAPIView(APIView):
    throttle_classes = [OTPPhoneThrottle, OTPIPThrottle]

    def post(self, request):
        user: User = request.user
        new_phone = request.data.get("phone_number")

        if not new_phone:
            raise APIError(OTPError.PHONE_REQUIRED)

        # Check state: must have verified old phone (step 2)
        cache_key = f"phone_change_step_{user.id}"
        state = cache.get(cache_key)

        if not state:
            raise APIError(OTPError.OTP_NOT_FOUND)

        if state.get("step") != "old_verified":
            raise APIError(OTPError.OLD_PHONE_VERIFICATION_REQUIRED)

        if user.phone_number == new_phone:
            raise APIError(UserAccountError.SAME_PHONE_AS_CURRENT)

        validate_phone(new_phone, user)

        # Generate OTP for new phone
        result = generate_otp(new_phone)

        # Update state: step 3 (store new phone)
        cache.set(
            cache_key,
            {
                "step": "new_otp_sent",
                "user_id": user.id,
                "new_phone": new_phone,
            },
            timeout=300,
        )

        if result:
            return Response(status=status.HTTP_200_OK)
        else:
            raise APIError(OTPError.NEW_PHONE_OTP_FAILED)


class PhoneChangeNewVerifyAPIView(APIView):
    throttle_classes = [OTPPhoneThrottle, OTPIPThrottle]

    def post(self, request):
        user: User = request.user
        otp = request.data.get("otp")

        if not otp:
            raise APIError(OTPError.PHONE_REQUIRED)

        # Check state: must be at step 3
        cache_key = f"phone_change_step_{user.id}"
        state = cache.get(cache_key)

        if not state:
            raise APIError(OTPError.OTP_NOT_FOUND)

        if state.get("step") != "new_otp_sent":
            raise APIError(OTPError.INVALID_STEP)

        new_phone = state.get("new_phone")

        if not new_phone:
            raise APIError(OTPError.NEW_PHONE_NOT_FOUND)

        # Verify OTP from new phone
        verify_otp(new_phone, otp)

        # Update user's phone number
        user.phone_number = new_phone
        user.save(update_fields=["phone_number", "updated_at"])

        # Clear state
        cache.delete(cache_key)

        return Response(
            {
                "user": UserProfileSerializer(
                    user,
                    context={
                        "request": request,
                    },
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class UserProfilePIView(APIView):
    serializer_class = UserProfileSerializer

    def get(self, request):
        user: User = request.user
        serializer = self.serializer_class(user, context={"request": request})

        return Response(
            {"user": serializer.data},
            status=status.HTTP_200_OK,
        )

    def put(self, request):
        user: User = request.user
        serializer = self.serializer_class(
            instance=user,
            data=request.data,
            context={"request": request},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        updated_user = serializer.save()

        return Response(
            {
                "user": self.serializer_class(
                    updated_user,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class CoachStudentPIView(APIView):
    pass


class GymMemberPIView(APIView):
    pass


class AdminUserPIView(APIView):
    pass
