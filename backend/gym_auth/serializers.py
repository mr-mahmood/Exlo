# gym_auth/serializers.py

from rest_framework import serializers
from .models import UserGymRole
from core.errors import APIError, GymLockerError
from users.serializers import UserBasicSerializer


class UserGymRoleSerializer(serializers.ModelSerializer):
    user = UserBasicSerializer(read_only=True)

    class Meta:
        model = UserGymRole
        fields = [
            "id",
            "user",
            "gym",
            "role",
            "created_at",
        ]

        read_only_fields = fields
