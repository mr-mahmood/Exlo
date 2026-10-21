# gym_locks/models.py

import uuid
from django.db import models, transaction
from django.db.models import Max
from gym.models import Gym
from users.models import User
from core.errors import APIError, GymLockerError


class GymLockerManager(models.Manager):

    @transaction.atomic
    def assign(self, gym, user) -> "GymLocker":

        User.objects.select_for_update().get(pk=user.pk)

        if self.filter(gym=gym, assigned_user=user).exists():
            raise APIError(GymLockerError.USER_ALREADY_ASSIGNED)

        locker: GymLocker = (
            self.select_for_update()
            .filter(gym=gym, is_active=True, assigned_user__isnull=True)
            .order_by("updated_at")
            .first()
        )  # type: ignore

        if locker is None:
            raise APIError(GymLockerError.NO_AVAILABLE_LOCKER)

        locker.assigned_user = user
        locker.save(update_fields=["assigned_user", "updated_at"])
        return locker

    @transaction.atomic
    def remove_assignment(self, gym, user) -> "GymLocker":

        locker: GymLocker = (
            self.select_for_update().filter(gym=gym, assigned_user=user).first()
        )  # type: ignore

        if locker is None:
            raise APIError(GymLockerError.USER_NOT_ASSIGNED)

        locker.assigned_user = None
        locker.save(update_fields=["assigned_user", "updated_at"])
        return locker

    @transaction.atomic
    def add_lockers(self, gym, count) -> list["GymLocker"]:

        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise APIError(GymLockerError.INVALID_LOCKER_NUMBER)

        # Prevent concurrent requests from allocating overlapping numbers.
        Gym.objects.select_for_update().get(id=gym.id)

        last_number = (
            self.filter(gym=gym).aggregate(last_number=Max("number"))["last_number"]
            or 0
        )

        lockers = [
            self.model(gym=gym, number=number)
            for number in range(last_number + 1, last_number + count + 1)
        ]

        return self.bulk_create(lockers)

    def get_gym_lockers(self, gym):
        return self.filter(gym=gym)

    def get_lock(self, gym, locker_id):
        try:
            return self.filter(id=locker_id, gym=gym).get()
        except GymLocker.DoesNotExist:
            raise APIError(GymLockerError.LOCKER_NOT_FOUND)

    def get_user_locker(self, gym, user) -> "GymLocker":
        locker = self.filter(gym=gym, assigned_user=user, is_active=True).first()
        if locker is None:
            raise APIError(GymLockerError.USER_NOT_ASSIGNED)
        return locker


class GymLocker(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    gym = models.ForeignKey(
        Gym,
        on_delete=models.CASCADE,
        related_name="lockers",
    )

    assigned_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)
    number = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: GymLockerManager = GymLockerManager()

    class Meta:
        db_table = "gym_lockers"
        ordering = ["-created_at"]
        unique_together = [["gym", "number"]]
        constraints = [
            models.UniqueConstraint(
                fields=["gym", "assigned_user"],
                condition=models.Q(assigned_user__isnull=False),
                name="unique_assigned_locker_per_user_per_gym",
            ),
        ]
        indexes = [
            models.Index(fields=["gym", "is_active", "assigned_user"]),
        ]

    def __str__(self):
        return f"{self.gym.name} - Locker {self.number}"

    def activate(self):
        if self.is_active == False:
            self.is_active = True
            self.save(update_fields=["is_active", "updated_at"])

    def deactivate(self):
        if self.is_active == True:
            self.is_active = False
            self.save(update_fields=["is_active", "updated_at"])
