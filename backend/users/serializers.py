from django.db import IntegrityError
from rest_framework import serializers
from users.models import User
from core.errors import APIError, SignUpError
from users.validators import (
    validate_name,
    validate_date_of_birth,
    validate_phone,
)


class UserSignupSerializer(serializers.ModelSerializer):

    # Core fields
    phone_number = serializers.CharField(required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    gender = serializers.ChoiceField(choices=User.Gender.choices, required=True)
    date_of_birth = serializers.DateField(required=True)
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
            "date_of_birth",
            "gender",
            "referral",  # referral code of users that reffer this user
            "profile_picture",
            "referral_code",  # user its own referral code
        ]

        read_only_fields = [
            "profile_picture",
            "referral_code",
        ]

    def validate_phone_number(self, value):
        return validate_phone(value)

    def validate_first_name(self, value):
        return validate_name(value)

    def validate_last_name(self, value):
        return validate_name(value)

    def validate_date_of_birth(self, value):
        return validate_date_of_birth(value)

    def validate_referral(self, value):
        #no referral)
        if not value or value.strip() == "":
            return None
        
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

    # Core fields
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    date_of_birth = serializers.DateField()
    gender = serializers.ChoiceField(choices=User.Gender.choices)
    profile_picture = serializers.ImageField()

    class Meta:
        model = User

        fields = [
            "phone_number",
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "referral_code",
            "profile_picture",
        ]

        read_only_fields = [
            "phone_number",
            "referral_code",
        ]

    def validate_first_name(self, value):
        return validate_name(value)

    def validate_last_name(self, value):
        return validate_name(value)

    def validate_date_of_birth(self, value):
        return validate_date_of_birth(value)
