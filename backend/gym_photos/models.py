# gym_photos/models.py

import uuid
from django.db import models
from gym.models import Gym


def gym_picture_path(instance, filename):
    return f"gym_photos/{uuid.uuid7().hex}.webp"


class GymPhotos(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    gym = models.ForeignKey(
        to=Gym,
        on_delete=models.CASCADE,
        related_name="photos",
    )

    photo = models.ImageField(
        upload_to=gym_picture_path,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gym_photos"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.gym.name} photo - {self.created_at}"
