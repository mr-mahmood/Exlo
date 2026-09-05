# gym/serializers.py

import os
import io
import secrets
from PIL import Image
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from rest_framework import serializers
from .models import Gym, GymPhotos
from core.errors import APIError, GymError


class GymPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = GymPhotos
        fields = [
            "id",
            "photo",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
        ]

    def validate_photo(self, value):
        if not value or value.size == 0:
            raise APIError(GymError.PHOTO_FILE_EMPTY)

        if value.size > settings.MAX_IMAGE_SIZE:
            raise APIError(GymError.PHOTO_FILE_TOO_LARGE)

        ext = os.path.splitext(value.name)[1].lower()
        allowed_extensions = [".jpg", ".jpeg", ".png", ".webp", ".gif"]
        if ext not in allowed_extensions:
            raise APIError(GymError.INVALID_PHOTO_EXTENSION)

        try:
            img = Image.open(value)
            img.verify()
            value.seek(0)
        except Exception as e:
            raise APIError(GymError.INVALID_PHOTO_FILE)

        return value

    def validate(self, data):
        if "photo" not in data or not data["photo"]:
            raise APIError(GymError.PHOTO_FILE_REQUIRED)
        return data

    def create(self, validated_data):
        photo = validated_data.pop("photo")
        gym = self.context["gym"]

        webp_file = self.convert_to_webp(photo)

        return GymPhotos.objects.create(
            photo=webp_file,
            gym=gym,
        )

    def convert_to_webp(self, image_file):
        try:
            img = Image.open(image_file)

            if img.mode not in ["RGB", "RGBA"]:
                img = img.convert("RGB")

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

        except Exception as e:
            raise APIError(GymError.IMAGE_CONVERSION_FAILED)


class GymSerializer(serializers.ModelSerializer):
    photos = GymPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Gym
        fields = [
            "id",
            "name",
            "gym_code",
            "province",
            "city",
            "address",
            "latitude",
            "longitude",
            "is_active",
            "photos",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "gym_code",
            "photos",
            "created_at",
        ]

    def validate(self, data):
        required_fields = ["name", "province", "city", "address"]

        is_create = not self.instance
        if is_create:
            for field in required_fields:
                if not data.get(field):
                    raise APIError(GymError.MISSING_GYM_DATA)

        return data
