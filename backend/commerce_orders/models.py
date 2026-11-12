# commerce_orders/models.py

import uuid
from django.db import models
from users.models import User
from commerce_products.models import CommerceProduct


class OrderManager(models.Manager):
    pass


class Order(models.Model):

    class Status(models.TextChoices):
        PENDING = "PENDING"
        SUCCEEDED = "SUCCEEDED"
        FAILED = "FAILED"

    class SettlementStatus(models.TextChoices):
        HELD = "HELD"  # The platform has not released the seller's revenue.
        RELEASED = "RELEASED"  # The seller's wallet has been credited successfully.
        VOIDED = "VOIDED"  # The seller will not receive this revenue, for example because the purchase was refunded.

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    commerce_product = models.ForeignKey(
        CommerceProduct,
        on_delete=models.PROTECT,
        related_name="orders",
    )

    buyer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="orders",
    )

    seller = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="sales",
    )

    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.PENDING,
    )

    settlement_status = models.CharField(
        max_length=20,
        choices=SettlementStatus.choices,
        default=SettlementStatus.HELD,
    )

    product_snapshot = models.JSONField()

    subtotal_amount = models.PositiveBigIntegerField(default=0)
    discount_amount = models.PositiveBigIntegerField(default=0)
    tax_amount = models.PositiveBigIntegerField(default=0)

    succeeded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: OrderManager = OrderManager()

    class Meta:
        db_table = "order"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["buyer"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(settlement_status="RELEASED")
                    | models.Q(status="SUCCEEDED")
                ),
                name="order_released_requires_success",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_amount__lt=models.F("subtotal_amount")),
                name="order_discount_less_than_subtotal",
            ),
        ]

    @property
    def total_amount(self) -> int:
        return self.subtotal_amount - self.discount_amount + self.tax_amount

    @property
    def is_refundable(self):
        if self.commerce_product.product_type == CommerceProduct.ProductType.GYM_MEMBERSHIP:
            return self.gym_subscription.is_refundable

    def cancel_purchased_product(self):
        if self.commerce_product.product_type == CommerceProduct.ProductType.GYM_MEMBERSHIP:
            return self.gym_subscription.cancel()

    def mark_settlement_voided(self):
        if self.settlement_status == Order.SettlementStatus.HELD:
            self.settlement_status = Order.SettlementStatus.VOIDED
            self.save(update_fields=["settlement_status", "updated_at"])

    def mark_settlement_released(self):
        if self.settlement_status == Order.SettlementStatus.HELD:
            self.settlement_status = Order.SettlementStatus.RELEASED
            self.save(update_fields=["settlement_status", "updated_at"])
