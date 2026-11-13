# commerce_wallet/models.py

import uuid
from django.db import models
from core.errors import APIError, WalletError
from users.models import User


class WalletManager(models.Manager):
    pass


class Wallet(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    owner = models.OneToOneField(
        User,
        on_delete=models.PROTECT,
        related_name="wallet",
        db_index=True,
    )

    balance = models.PositiveBigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: WalletManager = WalletManager()

    class Meta:
        db_table = "wallet"
        ordering = ["-created_at"]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(balance__gte=0),
                name="wallet_balance_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.owner.phone_number} -> {self.balance:,} Rial"

    def credit(self, amount):
        if amount > 0:
            self.balance += amount
            self.save(update_fields=["balance", "updated_at"])

    def debit(self, amount):
        if amount > 0:
            if self.balance - amount < 0:
                raise APIError(WalletError.BALANCE_NOT_ENOUGH)

            self.balance -= amount
            self.save(update_fields=["balance", "updated_at"])
