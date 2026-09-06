# gym/models.py

import uuid
import secrets
from django.db import models


class Gym(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=255,
    )

    gym_code = models.CharField(
        max_length=6,
        unique=True,
        editable=False,
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

    class Meta:
        db_table = "gym"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["gym_code"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.gym_code})"

    def _generate_unique_gym_code(self):
        while True:
            CHARACTERS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
            LENGTH = 6

            code = "".join(secrets.choice(CHARACTERS) for _ in range(LENGTH))

            if not Gym.objects.filter(gym_code=code):
                return code

    def save(self, *args, **kwargs):
        """Auto-generate gym_code on creation."""
        if not self.gym_code:
            self.gym_code = self._generate_unique_gym_code()
        super().save(*args, **kwargs)

    def activate(self):
        self.is_active = True
        self.save(update_fields=["is_active", "updated_at"])

    def deactivate(self):
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    # TODO: add the logic once the memebership tables and other part added to app
    def has_active_memberships(self):
        return False
