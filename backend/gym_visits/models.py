# gym_visits/models.py

import uuid
from django.db import IntegrityError, models, transaction
from django.db.models import Q, F
from django.utils import timezone
from gym.models import Gym
from gym_subscriptions.models import GymSubscription
from users.models import User
from core.errors import APIError, GymVisitsError, GymSubscriptionError


class GymVisitManager(models.Manager):

    def check_in(self, user, gym, subscription, method) -> "GymVisit":

        if self.filter(user=user, checked_out_at__isnull=True).exists():
            raise APIError(GymVisitsError.ALREADY_CHECKED_IN)

        try:
            return self.create(
                user=user,
                gym=gym,
                subscription=subscription,
                checked_in_at=timezone.now(),
                checked_in_method=method,
            )
        except IntegrityError as e:
            if "gym_visit_unique_open_per_user" in str(e):
                raise APIError(GymVisitsError.ALREADY_CHECKED_IN)
            raise


class GymVisit(models.Model):
    class Method(models.TextChoices):
        NFC = "NFC", "Nfc"
        QR = "QR", "QR"
        STAFF = "STAFF", "Staff"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="gym_visits",
    )

    gym = models.ForeignKey(
        Gym,
        on_delete=models.PROTECT,
        related_name="gym_visits",
    )

    subscription = models.ForeignKey(
        GymSubscription,
        on_delete=models.PROTECT,
        related_name="gym_visits",
    )

    checked_in_at = models.DateTimeField()
    checked_in_method = models.CharField(
        max_length=255,
        choices=Method.choices,
        default=Method.NFC,
    )

    checked_out_at = models.DateTimeField(null=True, blank=True)
    checked_out_method = models.CharField(
        max_length=255,
        choices=Method.choices,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: GymVisitManager = GymVisitManager()

    class Meta:
        db_table = "gym_visit"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["user", "checked_out_at"]),
            models.Index(fields=["user", "gym", "checked_out_at"]),
            models.Index(fields=["created_at"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(checked_out_at__isnull=True)
                | Q(checked_out_at__gte=F("checked_in_at")),
                name="gym_visit_checkout_after_checkin",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(checked_out_at__isnull=True),
                name="gym_visit_unique_open_per_user",
            ),
        ]

    def __str__(self):
        status = "IN " if self.checked_out_at is None else "OUT"
        return f"{status} {self.user} - {self.gym} - {self.checked_in_at}"

    @property
    def duration(self):
        if self.checked_out_at is None:
            return None
        return self.checked_out_at - self.checked_in_at

    def check_out(self, method):
        if self.checked_out_at is not None:
            raise APIError(GymVisitsError.ALREADY_CHECKED_OUT)

        now = timezone.now()
        if now < self.checked_in_at:
            raise APIError(GymVisitsError.INVALID_CHECKOUT_TIME)

        self.checked_out_at = now
        self.checked_out_method = method

        try:
            with transaction.atomic():
                self.save(
                    update_fields=[
                        "checked_out_at",
                        "checked_out_method",
                        "updated_at",
                    ]
                )
        except IntegrityError as e:
            if "gym_visit_checkout_after_checkin" in str(e):
                raise APIError(GymVisitsError.INVALID_CHECKOUT_TIME)
            raise

        return self
