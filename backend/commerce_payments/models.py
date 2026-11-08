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

    # called when want to top up the wallet
    def create_wallet_top_up(self, *, wallet, amount) -> "Payment":
        return self.create(
            wallet=wallet,
            payment_method=Payment.Method.ONLINE_GATEWAY,
            purpose=Payment.Purpose.WALLET_TOP_UP,
            amount=amount,
        )

    # Called when paying for an order using the wallet balance.
    def create_order_payment_wallet(self, *, order, wallet, amount) -> "Payment":
        return self.create(
            order=order,
            wallet=wallet,
            payment_method=Payment.Method.WALLET,
            purpose=Payment.Purpose.ORDER_PAYMENT,
            amount=amount,
            gateway_fee_amount=0,
        )

    # called when want to doa  ayment for order
    def create_order_payment_gateway(self, *, order, amount) -> "Payment":
        return self.create(
            order=order,
            payment_method=Payment.Method.ONLINE_GATEWAY,
            purpose=Payment.Purpose.ORDER_PAYMENT,
            amount=amount,
        )


class Payment(models.Model):

    # determine how does the user pay for order
    class Method(models.TextChoices):
        WALLET = "WALLET"
        ONLINE_GATEWAY = "ONLINE_GATEWAY"

    # determine why is this payment exist
    class Purpose(models.TextChoices):
        WALLET_TOP_UP = "WALLET_TOP_UP"
        ORDER_PAYMENT = "ORDER_PAYMENT"

    class Status(models.TextChoices):
        PENDING = "PENDING"
        SUCCEEDED = "SUCCEEDED"
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

    status = models.CharField(max_length=100, choices=Status.choices, default=Status.PENDING)
    payment_method = models.CharField(max_length=100, choices=Method.choices)
    purpose = models.CharField(max_length=100, choices=Purpose.choices)

    amount = models.PositiveBigIntegerField(default=0)
    gateway_fee_amount = models.PositiveBigIntegerField(default=settings.ZIBAL_IPG_FEE_MAX)

    paid_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom manager
    objects: PaymentManager = PaymentManager()

    class Meta:
        db_table = "payment"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["wallet", "-created_at"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="payment_amount_positive",
            ),
            models.CheckConstraint(
                condition=Q(gateway_fee_amount__gte=0),
                name="payment_gateway_fee_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(purpose="ORDER_PAYMENT", order__isnull=False)
                    & (
                        Q(
                            payment_method="WALLET",
                            wallet__isnull=False,
                            gateway_fee_amount=0,
                        )
                        | Q(
                            payment_method="ONLINE_GATEWAY",
                            wallet__isnull=True,
                        )
                    )
                )
                | Q(
                    purpose="WALLET_TOP_UP",
                    payment_method="ONLINE_GATEWAY",
                    order__isnull=True,
                    wallet__isnull=False,
                ),
                name="payment_valid_purpose_method_target",
            ),
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(
                    purpose="ORDER_PAYMENT",
                    status="SUCCEEDED",
                ),
                name="one_succeeded_order_payment",
            ),
        ]

    def __str__(self):
        return f"{self.purpose} -> {self.payment_method} -> {self.status}"

    def mark_succeeded(self):
        self.status = Payment.Status.SUCCEEDED
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at", "updated_at"])

    def mark_failed(self):
        self.status = Payment.Status.FAILED
        self.failed_at = timezone.now()
        self.save(update_fields=["status", "failed_at", "updated_at"])


class PaymentGatewayManager(models.Manager):
    pass


class PaymentGateway(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="gateway_payment",
    )

    track_id = models.BigIntegerField(unique=True)
    ref_num = models.CharField(max_length=255, blank=True, null=True)
    card_number = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Custom manager
    objects: PaymentGatewayManager = PaymentGatewayManager()

    class Meta:
        db_table = "payment_gateway_transaction"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.card_number} -> {self.ref_num}"

    def mark_verified(self, *, ref_num, card_number):
        self.ref_num = ref_num
        self.card_number = card_number
        self.save(update_fields=["ref_num", "card_number"])
