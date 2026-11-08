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
        PAID = "PAID"
        CANCELLED = "CANCELLED"
        REFUNDED = "REFUNDED"

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

    product_snapshot = models.JSONField()

    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.PENDING,
    )

    subtotal_amount = models.PositiveBigIntegerField(default=0)
    discount_amount = models.PositiveBigIntegerField(default=0)
    tax_amount = models.PositiveBigIntegerField(default=0)
    total_amount = models.PositiveBigIntegerField(default=0)

    paid_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom manager
    objects: OrderManager = OrderManager()

    class Meta:
        db_table = "order"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["buyer"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subtotal_amount__gte=0)
                & models.Q(discount_amount__gte=0)
                & models.Q(tax_amount__gte=0)
                & models.Q(total_amount__gte=0),
                name="order_amounts_nonnegative",
            ),
        ]
