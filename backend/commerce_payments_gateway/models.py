# commerce_payments_gateway/models.py

import uuid
from django.db import models
from commerce_payments.models import Payment


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
