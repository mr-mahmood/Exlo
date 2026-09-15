# gym_devices/serializers.py

from rest_framework import serializers
from .models import GymDevice
from gym.serializers import GymBasicSerializer


class GymDeviceSerializer(serializers.ModelSerializer):
    gym = GymBasicSerializer(read_only=True)

    class Meta:
        model = GymDevice
        fields = [
            "id",
            "gym",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
