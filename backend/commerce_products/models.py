# commerce_products/models.py

import uuid
from django.db import models


class CommerceProductManager(models.Manager):
    def create_gym_membership_product(self):
        return CommerceProduct.objects.create(
            product_type=CommerceProduct.ProductType.GYM_MEMBERSHIP,
        )


class CommerceProduct(models.Model):
    class ProductType(models.TextChoices):
        GYM_MEMBERSHIP = "GYM_MEMBERSHIP"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    product_type = models.CharField(
        max_length=255,
        choices=ProductType.choices,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects: CommerceProductManager = CommerceProductManager()

    class Meta:
        db_table = "commerce_product"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["product_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.id}"
