from django.db import IntegrityError
from rest_framework import serializers
from users.models import User
from core.errors import APIError, SignUpError

from users.validators import (
    validate_phone,
    validate_name,
    validate_date_of_birth,
)


class UserSignupSerializer(serializers.ModelSerializer):

    # Core fields
    phone_number = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    gender = serializers.ChoiceField(choices=User.Gender.choices)

    class Meta:
        model = User
        fields = [
            "phone_number",
            "first_name",
            "last_name",
            "gender",
        ]

    def validate_phone_number(self, value):
        return validate_phone(value)

    def validate_first_name(self, value):
        return validate_name(value)

    def validate_last_name(self, value):
        return validate_name(value)

    def create(self, validated_data):
        try:
            return User.objects.create_user(**validated_data)
        except IntegrityError:
            # Important condition check, DO NOT REMOVE
            # Extremely rare race condition where two requests
            # generated the same referral code at the same time
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
