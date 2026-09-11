# commerce_orders/models.py

import uuid
from django.db import models
from django.utils import timezone
from users.models import User
from commerce_products.models import CommerceProduct


# ============================================================================
# orders
# ============================================================================
class OrderManager(models.Manager):
    pass


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    buyer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="orders",
    )

    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.PENDING,
    )

    subtotal_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
    )

    discount_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    tax_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    total_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
    )

    paid_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Custom manager
    objects: OrderManager = OrderManager()

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]


# ============================================================================
# order items
# ============================================================================
class OrderItemManager(models.Manager):
    pass


class OrderItem(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    commerce_product = models.ForeignKey(
        CommerceProduct,
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )

    item_type = models.CharField(
        max_length=255,
        choices=CommerceProduct.ProductType.choices,
    )

    item_snapshot = models.JSONField()

    quantity = models.PositiveIntegerField()

    unit_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
    )

    subtotal_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
    )

    discount_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    tax_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    total_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    refundable_until = models.DateTimeField(null=True, blank=True)

    # Custom manager
    objects: OrderItemManager = OrderItemManager()

    class Meta:
        db_table = "order_items"
        ordering = ["-created_at"]

    @property
    def is_refundable(self):
        return (
            self.refundable_until is not None and self.refundable_until > timezone.now()
        )
