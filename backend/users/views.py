from uuid import uuid7

from redis.exceptions import RedisError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from users.serializers import UserSignupSerializer, UserProfileSerializer
from users.models import User
from users_referrals.models import Referral
from users_sessions.models import Session
from authentication.otp_service import OTPPurpose, OTPWorkflow, delete_if_unchanged, generate_otp, verify_otp
from authentication.token_services import create_tokens_for_user
from core.errors import APIError, OTPError, SignUpError, UserAccountError
from users.utils import normalize_phone
from users.validators import validate_phone
from typing import cast
from authentication.utils import (
    make_cookie,
    delete_cookies,
    signup_key,
    get_verified_signup_proof,
)


class UserSignupAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = UserSignupSerializer

    def post(self, request):
        phone_number = request.data.get("phone_number")

        if not phone_number:
            raise APIError(OTPError.PHONE_REQUIRED)

        phone_number = normalize_phone(phone_number)

        # Lock concurrent signup attempts for the same phone.
        lock = cache.lock(f"signup_verification_lock_{phone_number}", timeout=10)
        if not lock.acquire(blocking=False):
            raise APIError(SignUpError.SIGN_UP_NOT_ALLOWED)

        try:
            # Validate the signup proof.
            token = request.COOKIES.get("signup_token")

            proof = get_verified_signup_proof(phone_number, token)
            if proof is None:
                raise APIError(SignUpError.SIGN_UP_NOT_ALLOWED)

            # Validate signup data.
            data = request.data.copy()
            data["phone_number"] = phone_number

            serializer = self.serializer_class(
                data=data,
                context={"request": request, "normalized_phone": phone_number},
            )
            serializer.is_valid(raise_exception=True)

            # Verification may expire or be replaced while the form is validated.
            if not delete_if_unchanged(signup_key(phone_number), proof):
                raise APIError(SignUpError.SIGN_UP_NOT_ALLOWED)

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
                            "user": self.serializer_class(user, context={"request": request}).data,
                        },
                        status=status.HTTP_201_CREATED,
                    )

                    # Set authentication cookies.
                    make_cookie(
                        response,
                        {"access_token": access, "refresh_token": refresh},
                    )

                # Clear signup cookie after successful creation.
                delete_cookies(response, ["signup_token"], path=reverse("users:user-signup"))

                return response

            except IntegrityError:
                raise APIError(SignUpError.UNEXPECTED_ERROR)

        finally:
            if lock.owned():
                lock.release()


def _phone_change_state(user):
    key = f"phone_change_step_{user.pk}"
    try:
        return key, cache.get(key)
    except RedisError as exc:
        raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE) from exc


class PhoneChangeOldRequestAPIView(APIView):
    def post(self, request):
        with transaction.atomic():
            user: User = User.objects.select_for_update().get(pk=request.user.pk)
            cache_key = f"phone_change_step_{user.pk}"
            next_state = {
                "step": "old_otp_sent",
                "user_id": user.id,
                "flow_id": uuid7(),
                "old_phone": user.phone_number,
            }
            generate_otp(
                phone_number=user.phone_number,
                purpose=OTPPurpose.OLD_PHONE,
                user_id=user.pk,
                workflow=OTPWorkflow(cache_key, expected=None, next_state=next_state),
                publish_after_commit=True,
            )

        return Response(status=status.HTTP_200_OK)


class PhoneChangeOldVerifyAPIView(APIView):
    def post(self, request):
        user: User = request.user
        otp = request.data.get("otp")

        if not otp:
            raise APIError(OTPError.PHONE_REQUIRED)

        # Check state: must be at step 1
        cache_key, state = _phone_change_state(user)

        if not state:
            raise APIError(OTPError.OTP_NOT_FOUND)

        if state.get("step") != "old_otp_sent" or state.get("old_phone", user.phone_number) != user.phone_number:
            raise APIError(OTPError.INVALID_STEP)

        verify_otp(
            phone_number=user.phone_number,
            otp_code=otp,
            purpose=OTPPurpose.OLD_PHONE,
            user_id=user.pk,
            workflow=OTPWorkflow(cache_key, state, {**state, "step": "old_verified", "old_phone": user.phone_number}),
        )

        return Response(status=status.HTTP_200_OK)


class PhoneChangeNewRequestAPIView(APIView):
    def post(self, request):
        user: User = request.user
        new_phone = request.data.get("phone_number")

        if not new_phone:
            raise APIError(OTPError.PHONE_REQUIRED)

        # Check state: must have verified old phone (step 2)
        cache_key, state = _phone_change_state(user)

        if not state:
            raise APIError(OTPError.OTP_NOT_FOUND)

        step = state.get("step")
        old_phone = state.get("old_phone", user.phone_number)
        if step not in ("old_verified", "new_otp_sent") or old_phone != user.phone_number:
            raise APIError(OTPError.OLD_PHONE_VERIFICATION_REQUIRED)

        new_phone = normalize_phone(new_phone)
        if step == "new_otp_sent" and new_phone != state.get("new_phone"):
            raise APIError(OTPError.OLD_PHONE_VERIFICATION_REQUIRED)
        validate_phone(new_phone, instance=user)

        if user.phone_number == new_phone:
            raise APIError(UserAccountError.SAME_PHONE_AS_CURRENT)

        # A resend keeps the original verification window.
        next_state = None
        if step == "old_verified":
            next_state = {**state, "step": "new_otp_sent", "old_phone": user.phone_number, "new_phone": new_phone}
        generate_otp(
            phone_number=new_phone,
            purpose=OTPPurpose.NEW_PHONE,
            user_id=user.pk,
            workflow=OTPWorkflow(cache_key, state, next_state, conflict_error=OTPError.OLD_PHONE_VERIFICATION_REQUIRED),
        )

        return Response(status=status.HTTP_200_OK)


class PhoneChangeNewVerifyAPIView(APIView):
    def post(self, request):
        otp = request.data.get("otp")

        if not otp:
            raise APIError(OTPError.PHONE_REQUIRED)

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            cache_key, state = _phone_change_state(user)
            if not state:
                raise APIError(OTPError.OTP_NOT_FOUND)
            if state.get("step") != "new_otp_sent" or state.get("old_phone", user.phone_number) != user.phone_number:
                raise APIError(OTPError.INVALID_STEP)

            new_phone = state.get("new_phone")
            if not new_phone:
                raise APIError(OTPError.NEW_PHONE_NOT_FOUND)

            try:
                validate_phone(new_phone, instance=user)
            except APIError as exc:
                if exc.error_code == SignUpError.PHONE_NUMBER_REUSE[0]:
                    delete_if_unchanged(cache_key, state)
                raise

            verify_otp(
                phone_number=new_phone,
                otp_code=otp,
                purpose=OTPPurpose.NEW_PHONE,
                user_id=user.pk,
                workflow=OTPWorkflow(cache_key, state),
            )
            try:
                with transaction.atomic():
                    user.phone_number = new_phone
                    user.save(update_fields=["phone_number", "updated_at"])
            except IntegrityError:
                # Another account may claim the phone after validation. Query only
                # after the failed update's savepoint has been rolled back.
                if not User.objects.filter(phone_number=new_phone).exclude(pk=user.pk).exists():
                    raise
                delete_if_unchanged(cache_key, state)
                raise APIError(SignUpError.PHONE_NUMBER_REUSE)
            transaction.on_commit(lambda: delete_if_unchanged(cache_key, state))

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
