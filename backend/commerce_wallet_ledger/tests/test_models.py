from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from commerce_orders.models import Order
from commerce_payments.models import Payment
from commerce_products.models import CommerceProduct
from commerce_refunds.models import Refund
from commerce_wallet.models import Wallet
from commerce_wallet_ledger.models import WalletLedger
from users.models import User


class LedgerFixtures:
    def setUp(self):
        self.buyer = User.objects.create_user(phone_number="09120001005")
        self.wallet = Wallet.objects.create(owner=self.buyer, balance=100)
        product = CommerceProduct.objects.create(product_type="GYM_MEMBERSHIP")
        self.order = Order.objects.create(
            buyer=self.buyer, commerce_product=product, product_snapshot={}
        )
        self.payment = Payment.objects.create_order_payment_gateway(
            order=self.order, amount=100
        )
        self.refund = Refund.objects.create(
            order=self.order, payment=self.payment, amount=100,
            request_reason="Cancellation",
        )

    def make_entry(self, **overrides):
        return WalletLedger.objects.create(**{
            "wallet": self.wallet,
            "entry_type": WalletLedger.EntryType.CREDIT,
            "reason": WalletLedger.Reason.TOP_UP,
            "amount": 100,
            "balance_before": 100,
            **overrides,
        })


class WalletLedgerModelTests(LedgerFixtures, TestCase):
    def test_top_up_helper_only_creates_ledger_entry(self):
        top_up = Payment.objects.create_wallet_top_up(wallet=self.wallet, amount=25)

        entry = WalletLedger.objects.create_top_up_ledger(
            wallet=self.wallet, payment=top_up, amount=25, balance_before=100
        )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 100)
        self.assertEqual(entry.amount, 25)
        self.assertEqual(entry.balance_before, 100)
        self.assertEqual(entry.entry_type, WalletLedger.EntryType.CREDIT)
        self.assertEqual(entry.reason, WalletLedger.Reason.TOP_UP)

    def test_wallet_history_index_exists_in_database(self):
        with connection.cursor() as cursor:
            indexes = connection.introspection.get_constraints(
                cursor, WalletLedger._meta.db_table
            )
        self.assertTrue(any(
            item["index"] and item["columns"] == ["wallet_id", "created_at"]
            for item in indexes.values()
        ))

    def test_valid_credit_and_refund_entries(self):
        credit = self.make_entry()
        refund_entry = self.make_entry(
            reason=WalletLedger.Reason.REFUND, refund=self.refund
        )
        self.assertEqual(credit.pk.version, 7)
        self.assertEqual(refund_entry.refund, self.refund)

    def test_database_rejects_nonpositive_amount_and_negative_balance(self):
        for fields in ({"amount": 0}, {"amount": -1}, {"balance_before": -1}):
            with self.subTest(fields=fields):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        self.make_entry(**fields)

        entry = self.make_entry()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WalletLedger.objects.filter(pk=entry.pk).update(amount=0)

    def test_refund_requires_credit_and_unique_refund_link(self):
        invalid = (
            {"reason": WalletLedger.Reason.REFUND},
            {"refund": self.refund},
            {"reason": WalletLedger.Reason.REFUND, "refund": self.refund, "entry_type": WalletLedger.EntryType.DEBIT},
        )
        for fields in invalid:
            with self.subTest(fields=fields):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        self.make_entry(**fields)

        self.make_entry(reason=WalletLedger.Reason.REFUND, refund=self.refund)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_entry(reason=WalletLedger.Reason.REFUND, refund=self.refund)
