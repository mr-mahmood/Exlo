from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from users.models import User
from user_referrals.models import Referral
from core.errors import APIError, SignUpError
from users.validators import (
    validate_name,
    validate_date_of_birth,
    validate_phone,
)


class UserSignupSerializer(serializers.ModelSerializer):

    # Core fields
    phone_number = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    gender = serializers.ChoiceField(choices=User.Gender.choices)
    referral = serializers.CharField(
        required=False,
        write_only=True,
        allow_blank=True,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = [
            "phone_number",
            "first_name",
            "last_name",
            "gender",
            "referral",
        ]

    def validate_phone_number(self, value):
        return validate_phone(value)

    def validate_first_name(self, value):
        return validate_name(value)

    def validate_last_name(self, value):
        return validate_name(value)

    def validate_referral(self, value):
        if not value:
            return value

        # If referral code is provided, validate it exists
        if not User.objects.filter(referral_code=value).exists():
            raise APIError(SignUpError.REFERRAL_CODE_NOT_VALID)

        return value

    def create(self, validated_data):
        try:
            validated_data.pop("referral", None)
            return User.objects.create_user(**validated_data)
        except IntegrityError as e:
            # Important condition check, DO NOT REMOVE
            # This handles the rare race condition where two users get same referral_code
            # IntegrityError only happend for referral code becuase
            # other fildes checked before with custome validation
            raise APIError(SignUpError.UNEXPECTED_ERROR)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User

        fields = [
            "id",
            "phone_number",
            "first_name",
            "last_name",
            "profile_picture_url",
            "date_of_birth",
            "gender",
            "referral_code",
        ]

        read_only_fields = [
            "id",
            "phone_number",
            "referral_code",
        ]

    def validate_first_name(self, value):
        return validate_name(value)

    def validate_last_name(self, value):
        return validate_name(value)

    def validate_date_of_birth(self, value):
        return validate_date_of_birth(value)
