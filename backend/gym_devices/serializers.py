# gym_devices/serializers.py

from rest_framework import serializers
from .models import GymDevice
from gym.serializers import GymBasicSerializer
from core.errors import APIError, GymDeviceError


class GymDeviceSerializer(serializers.ModelSerializer):
    gym = GymBasicSerializer(read_only=True)

    device_type = serializers.CharField()

    class Meta:
        model = GymDevice
        fields = [
            "id",
            "gym",
            "device_type",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "gym",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def validate_device_type(self, value):
        valid_types = {
            GymDevice.GymDeviceType.ENTRANCE,
            GymDevice.GymDeviceType.LOCKER,
        }

        if value not in valid_types:
            raise APIError(GymDeviceError.INVALID_DEVICE_TYPE)

        return value
