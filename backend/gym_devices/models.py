# gym_devices/models.py

import uuid
import secrets
from django.db import models
from core.errors import APIError, GymDeviceError
from core.hashing import hash_secret, verify_secret
from gym.models import Gym


class GymDeviceManager(models.Manager):

    def get_device(self, device_id, gym) -> "GymDevice":
        device = self.filter(
            id=device_id,
            gym=gym,
            is_active=True,
        ).first()
        if device is None:
            raise APIError(GymDeviceError.DEVICE_NOT_FOUND)

        return device

    def find_device(self, gym, token: str) -> "GymDevice":
        if len(token) < 12:
            raise APIError(GymDeviceError.DEVICE_NOT_FOUND)

        prefix = token[:12]
        device = self.filter(
            gym=gym,
            token_prefix=prefix,
            is_active=True,
        ).first()

        if device is None or not verify_secret(token, device.token_hash):
            raise APIError(GymDeviceError.DEVICE_NOT_FOUND)

        return device

    def register_device(self, gym, device_type) -> tuple["GymDevice", str]:
        raw_token = self._generate_token()
        device = self.create(
            gym=gym,
            device_type=device_type,
            token_hash=hash_secret(raw_token),
            token_prefix=raw_token[:12],
        )
        return device, raw_token

    @staticmethod
    def _generate_token() -> str:
        return secrets.token_hex(32)


class GymDevice(models.Model):

    # type of esp 32 that send request can be for entrance/exit gate or lockers controler
    class GymDeviceType(models.TextChoices):
        ENTRANCE = "entrance", "Entrance"
        LOCKER = "locker", "Locker"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    gym = models.ForeignKey(
        Gym,
        on_delete=models.PROTECT,
        related_name="devices",
    )

    device_type = models.CharField(
        max_length=50,
        choices=GymDeviceType.choices,
    )

    token_hash = models.CharField(max_length=255)
    token_prefix = models.CharField(max_length=12, db_index=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: GymDeviceManager = GymDeviceManager()

    class Meta:
        db_table = "gym_device"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["gym", "is_active"]),
            models.Index(fields=["gym", "token_prefix"]),
            models.Index(fields=["gym", "device_type", "is_active"]),
            models.Index(fields=["gym", "token_prefix", "is_active"]),
            models.Index(fields=["token_prefix"]),
            models.Index(fields=["created_at"]),
        ]

    def revoke_device(self):
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])
