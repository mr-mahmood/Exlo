# gym_announcements/serializers.py

from django.db import transaction
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

    @transaction.atomic
    def create(self, validated_data):
        gym = self.context.get("gym")
        if not gym:
            raise APIError(GymAnnouncementError.GYM_REQUIRED)
        requested_status = validated_data.pop("status", GymAnnouncement.Status.DRAFT)
        validated_data["gym"] = gym
        announcement = super().create(validated_data)
        self._set_status(announcement, requested_status)
        return announcement

    @transaction.atomic
    def update(self, instance, validated_data):
        # Serialize edits against the latest state, including content-only updates.
        try:
            instance = GymAnnouncement.objects.select_for_update().get(
                pk=instance.pk, gym_id=instance.gym_id
            )
        except GymAnnouncement.DoesNotExist:
            raise APIError(GymAnnouncementError.ANNOUNCEMENT_NOT_FOUND)

        requested_status = validated_data.pop("status", instance.status)
        self._set_status(instance, requested_status)
        return super().update(instance, validated_data)

    def _set_status(self, announcement, requested_status):
        if requested_status == announcement.status:
            return
        if requested_status == GymAnnouncement.Status.PUBLISHED:
            announcement.publish()
        elif requested_status == GymAnnouncement.Status.ARCHIVED:
            announcement.archive()

        if announcement.status != requested_status:
            raise APIError(GymAnnouncementError.INVALID_STATUS_TRANSITION)
