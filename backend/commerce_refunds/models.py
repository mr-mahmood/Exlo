# commerce_refunds/models.py

import uuid
from django.db import models
from django.db.models import Q
from users.models import User


class RefundManager(models.Manager):
    pass


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    order = models.OneToOneField(
        "commerce_orders.Order",
        on_delete=models.PROTECT,
        related_name="refund",
    )

    payment = models.OneToOneField(
        "commerce_payments.Payment",
        on_delete=models.PROTECT,
        related_name="refund",
    )

    amount = models.PositiveBigIntegerField(default=0)

    status = models.CharField(
        max_length=255,
        choices=Status.choices,
        default=Status.PENDING_REVIEW,
    )

    requested_at = models.DateTimeField(auto_now_add=True)
    request_reason = models.TextField()
    review_note = models.TextField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by_admin = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="reviewed_refunds",
        null=True,
        blank=True,
    )

    refunded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: RefundManager = RefundManager()

    class Meta:
        db_table = "refund"
        ordering = ["-created_at"]
