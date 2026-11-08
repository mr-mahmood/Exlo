# commerce_wallet_ledger/models.py

import uuid
from django.db import models
from commerce_wallet.models import Wallet
from commerce_payments.models import Payment
from commerce_refunds.models import Refund
from commerce_orders.models import Order


class WalletLedgerManager(models.Manager):
    def create_top_up_ledger(self, *, wallet: Wallet, payment: Payment, amount, balance_before):
        return self.create(
            wallet=wallet,
            payment=payment,
            entry_type=WalletLedger.EntryType.CREDIT,
            amount=amount,
            balance_before=balance_before,
            reason=WalletLedger.Reason.TOP_UP,
        )


class WalletLedger(models.Model):
    class EntryType(models.TextChoices):
        CREDIT = "CREDIT"
        DEBIT = "DEBIT"

    class Reason(models.TextChoices):
        TOP_UP = "TOP_UP"
        ORDER_PAYMENT = "ORDER_PAYMENT"
        REFUND = "REFUND"
        SALE_REVENUE = "SALE_REVENUE"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        null=True,
        blank=True,
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        null=True,
        blank=True,
    )

    refund = models.OneToOneField(
        Refund,
        on_delete=models.PROTECT,
        related_name="ledger_entry",
        null=True,
        blank=True,
    )

    entry_type = models.CharField(max_length=255, choices=EntryType.choices)
    reason = models.CharField(max_length=255, choices=Reason.choices)
    amount = models.PositiveBigIntegerField(default=0)
    balance_before = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # Custom manager
    objects: WalletLedgerManager = WalletLedgerManager()

    class Meta:
        db_table = "wallet_ledger"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["wallet", "-created_at"])]

        constraints = [
            models.CheckConstraint(
                name="wallet_ledger_amount_positive",
                condition=models.Q(amount__gt=0),
            ),
            models.CheckConstraint(
                name="wallet_ledger_balance_before_nonnegative",
                condition=models.Q(balance_before__gte=0),
            ),
            models.CheckConstraint(
                name="wallet_ledger_refund_credit_only",
                condition=(
                    models.Q(reason="REFUND")
                    & models.Q(refund__isnull=False)
                    & models.Q(entry_type="CREDIT")
                )
                | (models.Q(refund__isnull=True) & ~models.Q(reason="REFUND")),
            ),
        ]
