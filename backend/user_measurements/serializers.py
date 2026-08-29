# user_measurements/serializers.py

from rest_framework import serializers
from .models import Measurements
from core.errors import MeasurementsError, APIError


class UserMeasurementSerializer(serializers.ModelSerializer):

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
            "measurement_notes",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
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
        """Validate that at least one measurement field is provided"""
        # List of measurement fields (all fields except id, created_at, updated_at, measurement_notes)
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

        # For create operations, require at least one measurement field
        if is_create:
            has_measurement = any(
                data.get(field) is not None for field in measurement_fields
            )
            if not has_measurement:
                # Check if there's any data at all
                if not data or all(value is None for value in data.values()):
                    raise APIError(MeasurementsError.MISSING_MEASUREMENT_DATA)

        return data
