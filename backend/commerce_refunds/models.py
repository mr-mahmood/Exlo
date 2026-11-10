# commerce_refunds/models.py

import uuid
from django.db import models
from django.utils import timezone
from users.models import User
from commerce_payments.models import Payment


class RefundManager(models.Manager):
    def create_wallet_top_up_refund(self, payment: Payment):
        return Refund.objects.create(
            payment=payment,
            amount=payment.amount,
            status=Refund.Status.APPROVED,
            request_reason="Wallet top-up processing failed in callback view.",
        )


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW"  # User submitted a refund request; admin has not decided
        APPROVED = "APPROVED"  # Admin accepted; waiting for processing
        REJECTED = "REJECTED"  # Admin declined; final state
        COMPLETED = "COMPLETED"  # Amount added to wallet

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
        default=Status.PENDING_REVIEW,
    )

    request_reason = models.TextField()
    review_note = models.TextField(null=True, blank=True)
    reviewed_by_admin = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="reviewed_refunds",
        null=True,
        blank=True,
    )

    reviewed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: RefundManager = RefundManager()

    class Meta:
        db_table = "refund"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Refund payment: {self.payment}"

    def mark_approved(self, *, admin_user, review_note):
        if self.status == Refund.Status.PENDING_REVIEW:
            self.status = Refund.Status.APPROVED
            self.reviewed_by_admin = admin_user
            self.review_note = review_note
            self.reviewed_at = timezone.now()
            self.save(update_fields=["status", "reviewed_by_admin", "review_note", "reviewed_at", "updated_at"])

    def mark_rejected(self, *, admin_user, review_note):
        if self.status == Refund.Status.PENDING_REVIEW:
            self.status = Refund.Status.REJECTED
            self.reviewed_by_admin = admin_user
            self.review_note = review_note
            self.reviewed_at = timezone.now()
            self.save(update_fields=["status", "reviewed_by_admin", "review_note", "reviewed_at", "updated_at"])

    def mark_completed(self):
        if self.status == Refund.Status.APPROVED:
            self.status = Refund.Status.COMPLETED
            self.refunded_at = timezone.now()
            self.save(update_fields=["status", "refunded_at", "updated_at"])
