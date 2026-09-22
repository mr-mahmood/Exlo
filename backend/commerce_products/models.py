# commerce_products/models.py

import uuid
from django.db import models


class CommerceProduct(models.Model):
    class ProductType(models.TextChoices):
        GYM_MEMBERSHIP = "GYM_MEMBERSHIP"

    # Primary Key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # Product Type
    product_type = models.CharField(
        max_length=255,
        choices=ProductType.choices,
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    # Meta
    class Meta:
        db_table = "commerce_product"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product_type"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["product_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.id}"
