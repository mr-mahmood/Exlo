# user_measurements/models.py

from decimal import Decimal
import uuid
from django.db import models
from users.models import User


class Measurements(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    user = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="measurements",
    )

    height_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )

    weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )

    chest_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )

    shoulders_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )

    biceps_left_cm = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    biceps_right_cm = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    forearms_left_cm = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    forearms_right_cm = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    waist_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )

    abdomen_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )

    hips_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )

    quadriceps_left_cm = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    quadriceps_right_cm = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    calves_left_cm = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    calves_right_cm = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    glutes_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )

    measurement_notes = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_measurements"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.created_at}"

    @property
    def bmi(self):
        if self.height_cm and self.weight_kg:
            height_m = self.height_cm / 100
            return Decimal(round(self.weight_kg / (height_m**2), 1))
        return None


def user_profile_picture_path(instance, filename):
    return f"measurement_photos/{uuid.uuid7().hex}.webp"


class MeasurementPhotos(models.Model):
    class PhotoType(models.TextChoices):
        FRONT = "FRONT"
        BACK = "BACK"
        SIDE = "SIDE"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    measurements = models.ForeignKey(
        to=Measurements,
        on_delete=models.CASCADE,
        related_name="photos",
    )

    type = models.CharField(
        max_length=20,
        choices=PhotoType.choices,
    )

    photo = models.ImageField(
        upload_to=user_profile_picture_path,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_measurement_photos"
        ordering = ["-created_at"]

        unique_together = [["measurements", "type"]]

        indexes = [
            models.Index(fields=["measurements"]),
            models.Index(fields=["measurements", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.measurements.user.get_full_name()} photo - {self.created_at}"
