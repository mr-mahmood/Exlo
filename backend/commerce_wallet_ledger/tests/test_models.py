from datetime import datetime, timezone

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from commerce_orders.models import Order
from commerce_payments.models import Payment
from commerce_wallet.models import Wallet
from commerce_wallet_ledger.models import WalletLedger
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from users.models import User


class WalletLedgerModelTests(TestCase):
    def setUp(self):
        super().setUp()
        self.now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        self.buyer = User.objects.create_user(phone_number="09120000001")
        self.seller = User.objects.create_user(phone_number="09120000002")
        self.other_user = User.objects.create_user(phone_number="09120000003")
        self.buyer_wallet = Wallet.objects.create(owner=self.buyer, balance=5000)
        self.seller_wallet = Wallet.objects.create(owner=self.seller, balance=700)
        self.other_wallet = Wallet.objects.create(owner=self.other_user, balance=900)
        self.gym = Gym.objects.create(name="Commerce test gym")
        self.plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Monthly membership",
            description="Commerce test membership",
            duration_months=1,
            visit_limit=30,
            price=1200,
        )

    def make_order(self, **values):
        return Order.objects.create(
            **{
                "commerce_product": self.plan.id,
                "buyer": self.buyer,
                "seller": self.seller,
                "subtotal_amount": 1200,
                "discount_amount": 200,
                "tax_amount": 50,
                "product_snapshot": {"name": "Monthly membership", "visit_limit": 30},
                "status": Order.Status.SUCCEEDED,
                "succeeded_at": self.now,
                **values,
            }
        )

    def make_top_up(self, **values):
        return Payment.objects.create(
            **{
                "wallet": self.buyer_wallet,
                "purpose": Payment.Purpose.WALLET_TOP_UP,
                "payment_method": Payment.Method.ONLINE_GATEWAY,
                "amount": 1050,
                "gateway_fee_amount": 250000,
                "status": Payment.Status.PAID,
                "paid_at": self.now,
                **values,
            }
        )

    def make_order_payment(self, order, **values):
        return Payment.objects.create(
            **{
                "order": order,
                "purpose": Payment.Purpose.ORDER_PAYMENT,
                "payment_method": Payment.Method.ONLINE_GATEWAY,
                "amount": 1050,
                "gateway_fee_amount": 250000,
                "status": Payment.Status.PAID,
                "paid_at": self.now,
                **values,
            }
        )

    def make_entry(self, **values):
        payment = values.pop("payment", None)
        return WalletLedger.objects.create(
            **{
                "wallet": self.buyer_wallet,
                "payment": payment if payment is not None else self.make_top_up(),
                "entry_type": "CREDIT",
                "reason": "TOP_UP",
                "amount": 1050,
                "balance_before": 5000,
                **values,
            }
        )

    def test_managers_persist_correct_credit_reason_amount_and_relationships(self):
        for method, reason in (
            ("create_top_up_ledger", "TOP_UP"),
            ("create_refund_ledger", "REFUND"),
            ("create_seller_revenue_ledger", "SALE_REVENUE"),
        ):
            with self.subTest(method=method):
                payment = (
                    self.make_top_up() if reason != "SALE_REVENUE" else self.make_order_payment(self.make_order())
                )
                wallet = self.buyer_wallet if reason != "SALE_REVENUE" else self.seller_wallet
                amount = 1050 if reason != "SALE_REVENUE" else 1000
                before = 5000 if reason != "SALE_REVENUE" else 700
                entry = getattr(WalletLedger.objects, method)(
                    wallet=wallet, payment=payment, amount=amount, balance_before=before
                )
                entry.refresh_from_db()
                self.assertEqual(entry.wallet_id, wallet.pk)
                self.assertEqual(entry.payment_id, payment.pk)
                self.assertEqual(entry.entry_type, "CREDIT")
                self.assertEqual(entry.reason, reason)
                self.assertEqual(entry.amount, amount)
                self.assertEqual(entry.balance_before, before)
                wallet.refresh_from_db()
                self.assertEqual(wallet.balance, before)

    def test_database_rejects_nonpositive_amounts_and_negative_starting_balance(self):
        for values in ({"amount": 0}, {"amount": -1}, {"balance_before": -1}):
            with self.subTest(values=values):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.make_entry(**values)

    def test_database_rejects_wrong_direction_for_each_reason(self):
        for reason, direction in (
            ("TOP_UP", "DEBIT"),
            ("REFUND", "DEBIT"),
            ("SALE_REVENUE", "DEBIT"),
            ("ORDER_PAYMENT", "CREDIT"),
            ("UNKNOWN", "CREDIT"),
            ("TOP_UP", "UNKNOWN"),
        ):
            with self.subTest(reason=reason, direction=direction):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.make_entry(reason=reason, entry_type=direction)

    def test_debit_can_use_exact_balance_but_cannot_exceed_it(self):
        order = self.make_order()
        payment = self.make_order_payment(
            order, payment_method="WALLET", wallet=self.buyer_wallet, gateway_fee_amount=0
        )
        entry = self.make_entry(payment=payment, reason="ORDER_PAYMENT", entry_type="DEBIT", amount=5000)
        self.assertEqual(entry.amount, 5000)
        with self.assertRaises(IntegrityError), transaction.atomic():
            WalletLedger.objects.filter(pk=entry.pk).update(amount=5001)
        entry.refresh_from_db()
        self.assertEqual(entry.amount, 5000)

    def test_payment_and_reason_are_unique_even_across_wallets(self):
        payment = self.make_top_up()
        self.make_entry(payment=payment)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_entry(payment=payment, wallet=self.other_wallet)
        self.make_entry(payment=payment, reason="REFUND")
        self.assertEqual(WalletLedger.objects.filter(payment=payment).count(), 2)

    def test_ledger_protects_wallet_and_payment_from_deletion(self):
        payment = self.make_top_up()
        self.make_entry(payment=payment, wallet=self.other_wallet)
        for target in (payment, self.other_wallet):
            with self.subTest(target=target.pk), self.assertRaises(ProtectedError):
                target.delete()
