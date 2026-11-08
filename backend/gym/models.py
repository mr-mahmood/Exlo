# gym/models.py

import uuid
import secrets
from django.db import models


class GymManager(models.Manager):

    def get_gym(self, gym_id, active_only=True) -> "Gym":
        try:
            queryset = self.filter(id=gym_id)

            if active_only:
                queryset = queryset.filter(is_active=True)

            return queryset.get()
        except Gym.DoesNotExist:
            from core.errors import APIError, GymError

            raise APIError(GymError.GYM_NOT_FOUND)


class Gym(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    name = models.CharField(
        max_length=255,
    )

    province = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    city = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    address = models.TextField(
        null=True,
        blank=True,
    )

    latitude = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    longitude = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: GymManager = GymManager()

    class Meta:
        db_table = "gym"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.name}"

    def activate(self):
        if self.is_active == False:
            self.is_active = True
            self.save(update_fields=["is_active", "updated_at"])

    def deactivate(self):
        if self.is_active == True:
            self.is_active = False
            self.save(update_fields=["is_active", "updated_at"])
