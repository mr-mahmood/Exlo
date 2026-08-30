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
        # no referral)
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


# users/serializers.py

from rest_framework import serializers
from django.conf import settings
from .models import User
from .validators import validate_name, validate_date_of_birth
from core.errors import UserAccountError, APIError
import os
import io
from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile


class UserProfileSerializer(serializers.ModelSerializer):
    # Core fields
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    date_of_birth = serializers.DateField()
    gender = serializers.ChoiceField(choices=User.Gender.choices)
    profile_picture = serializers.ImageField(required=False, allow_null=True)

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

    def validate_profile_picture(self, value):
        """Validate profile picture"""
        # Check if file exists
        if not value:
            return value

        # Check file size
        if value.size > settings.MAX_IMAGE_SIZE:
            raise APIError(UserAccountError.PROFILE_PICTURE_TOO_LARGE)

        # Check file extension
        ext = os.path.splitext(value.name)[1].lower()
        allowed_extensions = [".jpg", ".jpeg", ".png", ".webp"]
        if ext not in allowed_extensions:
            raise APIError(UserAccountError.INVALID_PROFILE_PICTURE_EXTENSION)

        # Validate it's a real image (PIL will raise error if not)
        try:
            img = Image.open(value)
            img.verify()  # Verify it's a valid image
            value.seek(0)  # Reset file pointer
        except Exception:
            raise APIError(UserAccountError.INVALID_PROFILE_PICTURE)

        return value

    def update(self, instance: User, validated_data):
        profile_picture = validated_data.pop("profile_picture", None)

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Handle profile picture if provided
        if profile_picture:
            # Convert to WebP
            converted_image = self.convert_to_webp(profile_picture)
            instance.profile_picture = converted_image

        instance.save()
        return instance

    def convert_to_webp(self, image_file):
        """Convert uploaded image to WebP format with reduced size"""
        try:
            # Open the image
            img = Image.open(image_file)

            # Convert to RGB if needed (for jpg compatibility)
            if img.mode not in ["RGB", "RGBA"]:
                img = img.convert("RGB")

            # Save to WebP
            output = io.BytesIO()
            img.save(output, format="WebP", quality=85, optimize=True)
            output.seek(0)

            # Create new file
            name = os.path.splitext(image_file.name)[0]
            webp_file = InMemoryUploadedFile(
                file=output,
                field_name=image_file.field_name,
                name=f"{name}.webp",
                content_type="image/webp",
                size=output.getbuffer().nbytes,
                charset=image_file.charset,
            )

            return webp_file

        except Exception:
            raise APIError(UserAccountError.PROFILE_PICTURE_CONVERSION_FAILED)
