# user_measurements/serializers.py

from rest_framework import serializers
from django.conf import settings
from .models import Measurements, MeasurementPhotos
from core.errors import MeasurementsError, APIError
import os
import io
from PIL import Image
from django.core.files.base import ContentFile


class MeasurementPhotosSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasurementPhotos
        fields = [
            "id",
            "type",
            "photo",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
        ]

    def validate_type(self, value):
        valid_types = [choice[0] for choice in MeasurementPhotos.PhotoType.choices]
        if value not in valid_types:
            raise APIError(MeasurementsError.INVALID_PHOTO_TYPE)
        return value

    def validate_photo(self, value):
        if value is None:
            raise APIError(MeasurementsError.PHOTO_FILE_REQUIRED)

        # Check file size
        if value.size > settings.MAX_IMAGE_SIZE:
            raise APIError(MeasurementsError.PHOTO_FILE_TOO_LARGE)

        # Check file extension
        ext = os.path.splitext(value.name)[1].lower()
        allowed_extensions = [".jpg", ".jpeg", ".png", ".webp"]
        if ext not in allowed_extensions:
            raise APIError(MeasurementsError.INVALID_PHOTO_EXTENSION)

        # Validate it's a real image (PIL will raise error if not)
        try:
            img = Image.open(value)
            img.verify()  # Verify it's a valid image
            value.seek(0)  # Reset file pointer
        except Exception:
            raise APIError(MeasurementsError.INVALID_PHOTO_TYPE)

        return value

    def validate(self, data):
        if "type" not in data or not data["type"]:
            raise APIError(MeasurementsError.PHOTO_TYPE_REQUIRED)

        if "photo" not in data or not data["photo"]:
            raise APIError(MeasurementsError.PHOTO_FILE_REQUIRED)

        return data

    def create(self, validated_data):
        photo = validated_data.pop("photo")
        webp_file = self.convert_to_webp(photo)

        return MeasurementPhotos.objects.create(
            **validated_data,
            photo=webp_file,
        )

    def convert_to_webp(self, photo):
        try:
            with Image.open(photo) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")

                output = io.BytesIO()
                img.save(output, format="WebP", quality=85, optimize=True)

            name = f"{os.path.splitext(photo.name)[0]}.webp"
            return ContentFile(output.getvalue(), name=name)

        except Exception:
            raise APIError(MeasurementsError.IMAGE_CONVERSION_FAILED)


class UserMeasurementSerializer(serializers.ModelSerializer):
    photos = MeasurementPhotosSerializer(many=True, read_only=True)

    class Meta:
        model = Measurements
        fields = [
            "id",
            "height_cm",
            "weight_kg",
            "chest_cm",
            "shoulders_cm",
            "biceps_left_cm",
            "biceps_right_cm",
            "forearms_left_cm",
            "forearms_right_cm",
            "waist_cm",
            "abdomen_cm",
            "hips_cm",
            "quadriceps_left_cm",
            "quadriceps_right_cm",
            "calves_left_cm",
            "calves_right_cm",
            "glutes_cm",
            "photos",
            "measurement_notes",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "photos",
            "created_at",
        ]

    def validate_height_cm(self, value):
        if value is not None:
            if value < 50 or value > 300:
                raise APIError(MeasurementsError.INVALID_HEIGHT)
        return value

    def validate_weight_kg(self, value):
        if value is not None:
            if value < 20 or value > 500:
                raise APIError(MeasurementsError.INVALID_WEIGHT)
        return value

    def validate_chest_cm(self, value):
        if value is not None:
            if value < 30 or value > 200:
                raise APIError(MeasurementsError.INVALID_CHEST)
        return value

    def validate_shoulders_cm(self, value):
        if value is not None:
            if value < 30 or value > 200:
                raise APIError(MeasurementsError.INVALID_SHOULDERS)
        return value

    def validate_biceps_left_cm(self, value):
        if value is not None:
            if value < 10 or value > 100:
                raise APIError(MeasurementsError.INVALID_BICEPS)
        return value

    def validate_biceps_right_cm(self, value):
        if value is not None:
            if value < 10 or value > 100:
                raise APIError(MeasurementsError.INVALID_BICEPS)
        return value

    def validate_forearms_left_cm(self, value):
        if value is not None:
            if value < 10 or value > 80:
                raise APIError(MeasurementsError.INVALID_FOREARMS)
        return value

    def validate_forearms_right_cm(self, value):
        if value is not None:
            if value < 10 or value > 80:
                raise APIError(MeasurementsError.INVALID_FOREARMS)
        return value

    def validate_waist_cm(self, value):
        if value is not None:
            if value < 40 or value > 250:
                raise APIError(MeasurementsError.INVALID_WAIST)
        return value

    def validate_abdomen_cm(self, value):
        if value is not None:
            if value < 40 or value > 250:
                raise APIError(MeasurementsError.INVALID_ABDOMEN)
        return value

    def validate_hips_cm(self, value):
        if value is not None:
            if value < 40 or value > 250:
                raise APIError(MeasurementsError.INVALID_HIPS)
        return value

    def validate_quadriceps_left_cm(self, value):
        if value is not None:
            if value < 20 or value > 150:
                raise APIError(MeasurementsError.INVALID_QUADRICEPS)
        return value

    def validate_quadriceps_right_cm(self, value):
        if value is not None:
            if value < 20 or value > 150:
                raise APIError(MeasurementsError.INVALID_QUADRICEPS)
        return value

    def validate_calves_left_cm(self, value):
        if value is not None:
            if value < 15 or value > 100:
                raise APIError(MeasurementsError.INVALID_CALVES)
        return value

    def validate_calves_right_cm(self, value):
        if value is not None:
            if value < 15 or value > 100:
                raise APIError(MeasurementsError.INVALID_CALVES)
        return value

    def validate_glutes_cm(self, value):
        if value is not None:
            if value < 40 or value > 250:
                raise APIError(MeasurementsError.INVALID_GLUTES)
        return value

    def validate(self, data):
        # List of measurement fields (all fields except id, created_at, updated_at, measurement_notes, photos)
        measurement_fields = [
            "height_cm",
            "weight_kg",
            "chest_cm",
            "shoulders_cm",
            "biceps_left_cm",
            "biceps_right_cm",
            "forearms_left_cm",
            "forearms_right_cm",
            "waist_cm",
            "abdomen_cm",
            "hips_cm",
            "quadriceps_left_cm",
            "quadriceps_right_cm",
            "calves_left_cm",
            "calves_right_cm",
            "glutes_cm",
        ]

        # Check if this is a create operation (no instance) or update (has instance)
        is_create = not self.instance
        if is_create:
            has_measurement = any(
                data.get(field) is not None for field in measurement_fields
            )
            if not has_measurement:
                # Check if there's any data at all
                if not data or all(value is None for value in data.values()):
                    raise APIError(MeasurementsError.MISSING_MEASUREMENT_DATA)

        return data
