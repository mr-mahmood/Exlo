# commerce_payments/models.py

import re
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from commerce_orders.models import Order
from commerce_wallet.models import Wallet


class PaymentManager(models.Manager):

    def create_wallet_top_up(self, *, wallet, amount) -> "Payment":
        return self.create(
            wallet=wallet,
            payment_method=Payment.Method.ONLINE_GATEWAY,
            purpose=Payment.Purpose.WALLET_TOP_UP,
            amount=amount,
        )

    def create_order_payment_wallet(self, *, order, wallet, amount) -> "Payment":
        return self.create(
            order=order,
            wallet=wallet,
            payment_method=Payment.Method.WALLET,
            purpose=Payment.Purpose.ORDER_PAYMENT,
            amount=amount,
            gateway_fee_amount=0,
        )

    def create_order_payment_gateway(self, *, order, amount) -> "Payment":
        return self.create(
            order=order,
            payment_method=Payment.Method.ONLINE_GATEWAY,
            purpose=Payment.Purpose.ORDER_PAYMENT,
            amount=amount,
        )


class Payment(models.Model):

    class Method(models.TextChoices):
        WALLET = "WALLET"
        ONLINE_GATEWAY = "ONLINE_GATEWAY"

    class Purpose(models.TextChoices):
        WALLET_TOP_UP = "WALLET_TOP_UP"
        ORDER_PAYMENT = "ORDER_PAYMENT"

    class Status(models.TextChoices):
        PENDING = "PENDING"
        PAID = "PAID"
        FAILED = "FAILED"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="payments",
        blank=True,
        null=True,
    )

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="payments",
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=100,
        choices=Status.choices,
        default=Status.PENDING,
    )

    payment_method = models.CharField(
        max_length=100,
        choices=Method.choices,
    )

    purpose = models.CharField(
        max_length=100,
        choices=Purpose.choices,
    )

    amount = models.PositiveBigIntegerField(default=0)
    gateway_fee_amount = models.PositiveBigIntegerField(default=settings.ZIBAL_IPG_FEE_MAX)

    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: PaymentManager = PaymentManager()

    class Meta:
        db_table = "payment"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["wallet"]),
        ]

    def __str__(self):
        return f"{self.purpose} -> {self.payment_method} -> {self.status}"

    def mark_paid(self):
        if self.status != Payment.Status.PAID:
            self.status = Payment.Status.PAID
            self.paid_at = timezone.now()
            self.save(update_fields=["status", "paid_at", "updated_at"])

    def mark_failed(self):
        if self.status != Payment.Status.FAILED:
            self.status = Payment.Status.FAILED
            self.save(update_fields=["status", "updated_at"])