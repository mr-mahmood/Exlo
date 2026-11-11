# gym_auth/models.py

import uuid
from django.db import IntegrityError, models, transaction
from users.models import User
from gym.models import Gym
from core.errors import APIError, UserGymRoleError


class UserGymRoleManager(models.Manager):

    def create_owner(self, user, gym):
        try:
            with transaction.atomic():
                return self._create_role(user, gym, UserGymRole.Role.OWNER)
        except IntegrityError as exc:
            if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None) == "unique_owner_per_gym":
                raise APIError(UserGymRoleError.OWNER_ALREADY_EXISTS) from exc
            raise

    def create_coach(self, user, gym):
        return self._create_role(user, gym, UserGymRole.Role.COACH)

    def create_staff(self, user, gym):
        return self._create_role(user, gym, UserGymRole.Role.STAFF)

    def _create_role(self, user, gym, role):
        assignment, created = self.get_or_create(user=user, gym=gym, role=role)
        if not created:
            raise APIError(UserGymRoleError.ROLE_ALREADY_EXISTS)
        return assignment


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

        constraints = [
            models.UniqueConstraint(
                fields=["gym"],
                condition=models.Q(role="OWNER"),
                name="unique_owner_per_gym",
            ),
        ]

        indexes = [
            models.Index(fields=["user", "role"]),
            models.Index(fields=["gym", "role"]),
            models.Index(fields=["user", "gym", "role"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.user.full_name} is {self.role} at {self.gym.name}"
