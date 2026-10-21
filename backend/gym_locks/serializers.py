# gym_locks/serializers.py

from rest_framework import serializers
from .models import GymLocker
from core.errors import APIError, GymLockerError


class GymLockerSerializer(serializers.ModelSerializer):

    class Meta:
        model = GymLocker
        fields = [
            "id",
            "gym",
            "assigned_user",
            "is_active",
            "number",
        ]

        read_only_fields = fields
