from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from rest_framework import serializers
from commerce_wallet.models import Wallet
from users.models import User
from core.errors import APIError, SignUpError
from users.validators import validate_name, validate_date_of_birth, validate_phone
from rest_framework import serializers
from django.conf import settings
from .models import User
from .validators import validate_name, validate_date_of_birth
from core.errors import UserAccountError, APIError
import os
import io
from PIL import Image


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
        if not User.objects.filter(referral_code=value):
            raise APIError(SignUpError.REFERRAL_CODE_NOT_VALID)

        return value

    def create(self, validated_data):
        validated_data.pop("referral", None)

        try:
            with transaction.atomic():
                user = User.objects.create_user(**validated_data)
                Wallet.objects.create(owner=user)
                return user
        except IntegrityError:
            # Important condition check, DO NOT REMOVE
            # This handles the rare race condition where two users get same referral_code.
            # IntegrityError only happens for referral code (other fields checked before
            # with custom validation) or wallet creation (OneToOneField duplicate).
            raise APIError(SignUpError.UNEXPECTED_ERROR)


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
        profile_picture = validated_data.pop("profile_picture", serializers.empty)
        previous_picture = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if profile_picture is None:
            default_picture = instance._meta.get_field("profile_picture").get_default()
            if (
                instance.profile_picture
                and instance.profile_picture.name != default_picture
            ):
                previous_picture = instance.profile_picture
            instance.profile_picture = default_picture
        elif profile_picture is not serializers.empty:
            converted_image = self.convert_to_webp(profile_picture)
            instance.profile_picture.save(
                converted_image.name,
                converted_image,
                save=False,
            )

        instance.save()

        if previous_picture:
            storage = previous_picture.storage
            name = previous_picture.name

            def delete_previous_picture():
                storage.delete(name)

            transaction.on_commit(delete_previous_picture, robust=True)

        return instance

    def convert_to_webp(self, image_file):
        """Convert uploaded image to WebP format with reduced size."""
        try:
            img = Image.open(image_file)

            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            output = io.BytesIO()
            img.save(output, format="WebP", quality=85, optimize=True)

            name = f"{os.path.splitext(image_file.name)[0]}.webp"
            return ContentFile(output.getvalue(), name=name)

        except Exception:
            raise APIError(UserAccountError.PROFILE_PICTURE_CONVERSION_FAILED)


class UserBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "phone_number",
            "first_name",
            "last_name",
        ]
        read_only_fields = [
            "phone_number",
            "first_name",
            "last_name",
        ]
