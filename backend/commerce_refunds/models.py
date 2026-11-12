# commerce_refunds/models.py

import uuid
from django.db import models
from django.utils import timezone
from commerce_payments.models import Payment


class RefundManager(models.Manager):
    def create_wallet_top_up_refund(self, payment: Payment):
        return self.create(payment=payment, amount=payment.amount)


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        COMPLETED = "COMPLETED"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="refund",
    )

    amount = models.PositiveBigIntegerField(default=0)

    status = models.CharField(
        max_length=255,
        choices=Status.choices,
        default=Status.PENDING,
    )

    refunded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: RefundManager = RefundManager()

    class Meta:
        db_table = "refund"
        ordering = ["-created_at"]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="refund_amount_positive",
            ),
        ]

    def __str__(self):
        return f"Refund payment: {self.payment}"

    def mark_completed(self):
        if self.status == Refund.Status.PENDING:
            self.status = Refund.Status.COMPLETED
            self.refunded_at = timezone.now()
            self.save(update_fields=["status", "refunded_at", "updated_at"])
