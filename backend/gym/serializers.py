# gym/serializers.py

from rest_framework import serializers
from .models import Gym
from core.errors import APIError, GymError
from gym_photos.serializers import GymPhotoSerializer


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


class GymBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gym
        fields = [
            "id",
            "name",
            "province",
            "city",
            "address",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "name",
            "province",
            "city",
            "address",
            "is_active",
        ]
