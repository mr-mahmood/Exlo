# gym_auth/models.py

import uuid
from django.db import models
from users.models import User
from gym.models import Gym


class UserGymRole(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER"
        STAFF = "STAFF"
        COACH = "COACH"
        ATHLETE = "ATHLETE"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="gyms",
        db_index=True,
    )

    gym = models.ForeignKey(
        Gym,
        on_delete=models.PROTECT,
        related_name="users",
        db_index=True,
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.ATHLETE,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_gym_role"
        ordering = ["-created_at"]

        unique_together = [["user", "gym", "role"]]

        indexes = [
            models.Index(fields=["user", "role"]),
            models.Index(fields=["gym", "role"]),
            models.Index(fields=["user", "gym", "role"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.user.full_name} is {self.role} at {self.gym.name}"

    @property
    def is_owner(self) -> bool:
        return self.role == UserGymRole.Role.OWNER

    @property
    def is_staff(self) -> bool:
        return self.role == UserGymRole.Role.STAFF

    @property
    def is_coach(self) -> bool:
        return self.role == UserGymRole.Role.COACH

    @property
    def is_athlete(self) -> bool:
        return self.role == UserGymRole.Role.ATHLETE
