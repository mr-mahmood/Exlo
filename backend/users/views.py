from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from users.serializers import UserSignupSerializer, UserProfileSerializer
from users.models import User
from users_referrals.models import Referral
from users_sessions.models import Session
from authentication.otp_service import OTPPurpose, generate_otp, verify_otp
from authentication.token_services import create_tokens_for_user
from core.errors import APIError, OTPError, SignUpError, UserAccountError
from users.validators import validate_phone
from typing import cast
from authentication.utils import (
    make_cookie,
    delete_cookies,
    signup_key,
    verify_signup_proof,
    SIGNUP_PATH,
)


class UserSignupAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = UserSignupSerializer

    def post(self, request):
        phone_number = request.data.get("phone_number")

        if not phone_number:
            raise APIError(OTPError.PHONE_REQUIRED)

        phone_number = validate_phone(phone_number, skip_duplicate_check=True)

        # Lock concurrent signup attempts for the same phone.
        lock = cache.lock(f"signup_verification_lock_{phone_number}", timeout=10)
        if not lock.acquire(blocking=False):
            raise APIError(SignUpError.SIGN_UP_NOT_ALLOWED)

        try:
            # Validate the signup proof.
            token = request.COOKIES.get("signup_token")

            if not verify_signup_proof(phone_number, token):
                raise APIError(SignUpError.SIGN_UP_NOT_ALLOWED)

            # One verified OTP permits one signup attempt.
            # Consume the proof before processing the signup.
            if not cache.delete(signup_key(phone_number)):
                raise APIError(SignUpError.SIGN_UP_NOT_ALLOWED)

            # Validate signup data.
            data = request.data.copy()
            data["phone_number"] = phone_number

            serializer = self.serializer_class(
                data=data,
                context={"request": request},
            )
            serializer.is_valid(raise_exception=True)

            referral_code = serializer.validated_data.get("referral")

            try:
                with transaction.atomic():
                    # Create user.
                    user = cast(User, serializer.save())

                    # Create referral if provided.
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

                    # Create session and JWT tokens.
                    session = Session.create_session(user, request)
                    access, refresh = create_tokens_for_user(user, session)

                    # Prepare response.
                    response = Response(
                        {
                            "user": self.serializer_class(
                                user,
                                context={"request": request},
                            ).data,
                        },
                        status=status.HTTP_201_CREATED,
                    )

                    # Set authentication cookies.
                    make_cookie(
                        response,
                        {
                            "access_token": access,
                            "refresh_token": refresh,
                        },
                    )

                # Clear signup cookie after successful creation.
                delete_cookies(
                    response,
                    ["signup_token"],
                    path=SIGNUP_PATH,
                )

                return response

            except IntegrityError:
                raise APIError(SignUpError.UNEXPECTED_ERROR)

        finally:
            if lock.owned():
                lock.release()


class PhoneChangeOldRequestAPIView(APIView):
    def post(self, request):
        user: User = request.user

        # Generate OTP for current phone
        generate_otp(phone_number=user.phone_number, purpose=OTPPurpose.OLD_PHONE, user_id=user.pk)

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

        return Response(status=status.HTTP_200_OK)


class PhoneChangeOldVerifyAPIView(APIView):
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
        verify_otp(phone_number=user.phone_number, otp_code=otp, purpose=OTPPurpose.OLD_PHONE, user_id=user.pk)

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

        step = state.get("step")
        if step == "new_otp_sent":
            new_phone = validate_phone(new_phone, skip_duplicate_check=True)
            if new_phone != state.get("new_phone"):
                raise APIError(OTPError.OLD_PHONE_VERIFICATION_REQUIRED)
        elif step != "old_verified":
            raise APIError(OTPError.OLD_PHONE_VERIFICATION_REQUIRED)

        new_phone = validate_phone(new_phone, instance=user)

        if user.phone_number == new_phone:
            raise APIError(UserAccountError.SAME_PHONE_AS_CURRENT)

        # Generate OTP for new phone
        generate_otp(phone_number=new_phone, purpose=OTPPurpose.NEW_PHONE, user_id=user.pk)

        if step == "new_otp_sent":
            return Response(status=status.HTTP_200_OK)

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

        return Response(status=status.HTTP_200_OK)


class PhoneChangeNewVerifyAPIView(APIView):
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

        try:
            new_phone = validate_phone(new_phone, instance=user)
        except APIError as exc:
            if exc.error_code == SignUpError.PHONE_NUMBER_REUSE[0]:
                cache.delete(cache_key)
            raise

        # Verify OTP from new phone
        verify_otp(phone_number=new_phone, otp_code=otp, purpose=OTPPurpose.NEW_PHONE, user_id=user.pk)

        old_phone = user.phone_number
        try:
            with transaction.atomic():
                user.phone_number = new_phone
                user.save(update_fields=["phone_number", "updated_at"])
                transaction.on_commit(lambda: cache.delete(cache_key))
        except IntegrityError:
            user.phone_number = old_phone
            # Another account may claim the phone after validation. Query only
            # after the failed update's savepoint has been rolled back.
            if User.objects.filter(phone_number=new_phone).exclude(pk=user.pk).exists():
                cache.delete(cache_key)
                raise APIError(SignUpError.PHONE_NUMBER_REUSE)
            raise

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


class UserProfileDetailAPIView(APIView):
    serializer_class = UserProfileSerializer

    def get(self, request):
        user: User = request.user
        serializer = self.serializer_class(user, context={"request": request})

        return Response(
            {"user": serializer.data},
            status=status.HTTP_200_OK,
        )


class UserProfileUpdateAPIView(APIView):
    serializer_class = UserProfileSerializer

    def put(self, request):
        user: User = request.user
        serializer = self.serializer_class(
            instance=user,
            data=request.data,
            context={"request": request},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "user": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class CoachStudentPIView(APIView):
    pass


class GymMemberPIView(APIView):
    pass


class AdminUserPIView(APIView):
    pass
