# gym_announcements/serializers.py

from rest_framework import serializers
from .models import GymAnnouncement
from core.errors import APIError, GymAnnouncementError
from users.serializers import UserBasicSerializer


class GymAnnouncementSerializer(serializers.ModelSerializer):
    author = UserBasicSerializer(read_only=True)

    class Meta:
        model = GymAnnouncement
        fields = [
            "id",
            "author",
            "title",
            "content",
            "status",
            "published_at",
            "archived_at",
        ]
        read_only_fields = [
            "id",
            "published_at",
            "archived_at",
        ]

    def create(self, validated_data):
        gym = self.context.get("gym")
        if not gym:
            raise APIError(GymAnnouncementError.GYM_REQUIRED)
        validated_data["gym"] = gym
        return super().create(validated_data)
