# gym_auth/models.py

import uuid
from django.db import models
from users.models import User
from gym.models import Gym


class UserGymRoleManager(models.Manager):

    def create_owner(self, user, gym):
        return self.create(
            user=user,
            gym=gym,
            role=UserGymRole.Role.OWNER,
        )

    def create_coach(self, user, gym):
        return self.create(
            user=user,
            gym=gym,
            role=UserGymRole.Role.COACH,
        )

    def create_staff(self, user, gym):
        return self.create(
            user=user,
            gym=gym,
            role=UserGymRole.Role.STAFF,
        )


class UserGymRole(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER"
        COACH = "COACH"
        STAFF = "STAFF"

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
        default=Role.STAFF,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects: UserGymRoleManager = UserGymRoleManager()

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
