# commerce_wallet_ledger/models.py

import uuid
from django.db import models
from commerce_wallet.models import Wallet
from commerce_payments.models import Payment


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

    def create_refund_ledger(self, *, wallet: Wallet, payment: Payment, amount, balance_before):
        return self.create(
            wallet=wallet,
            payment=payment,
            entry_type=WalletLedger.EntryType.CREDIT,
            reason=WalletLedger.Reason.REFUND,
            amount=amount,
            balance_before=balance_before,
        )

    def create_seller_revenue_ledger(self, *, wallet: Wallet, payment: Payment, amount, balance_before):
        return self.create(
            wallet=wallet,
            payment=payment,
            entry_type=WalletLedger.EntryType.CREDIT,
            reason=WalletLedger.Reason.SALE_REVENUE,
            amount=amount,
            balance_before=balance_before,
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
    )

    entry_type = models.CharField(max_length=255, choices=EntryType.choices)
    reason = models.CharField(max_length=255, choices=Reason.choices)
    amount = models.PositiveBigIntegerField(default=0)
    balance_before = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects: WalletLedgerManager = WalletLedgerManager()

    class Meta:
        db_table = "wallet_ledger"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["wallet"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="wallet_ledger_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(reason="ORDER_PAYMENT", entry_type="DEBIT")
                    | models.Q(
                        reason__in=["TOP_UP", "REFUND", "SALE_REVENUE"],
                        entry_type="CREDIT",
                    )
                ),
                name="wallet_ledger_valid_direction",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(entry_type="DEBIT")
                    | models.Q(amount__lte=models.F("balance_before"))
                ),
                name="wallet_ledger_debit_within_balance",
            ),
            models.UniqueConstraint(
                fields=["payment", "reason"],
                name="unique_wallet_ledger_reason_per_payment",
            ),
        ]
