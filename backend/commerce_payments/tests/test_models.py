from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from commerce_orders.models import Order
from commerce_payments.models import Payment
from commerce_wallet.models import Wallet
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from users.models import User


class PaymentModelTests(TestCase):
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

    def test_top_up_manager_creates_pending_gateway_payment(self):
        payment = Payment.objects.create_wallet_top_up(wallet=self.buyer_wallet, amount=1050)

        payment.refresh_from_db()
        self.assertEqual(payment.wallet_id, self.buyer_wallet.pk)
        self.assertIsNone(payment.order_id)
        self.assertEqual(payment.purpose, "WALLET_TOP_UP")
        self.assertEqual(payment.payment_method, "ONLINE_GATEWAY")
        self.assertEqual(payment.status, "PENDING")
        self.assertEqual(payment.amount, 1050)
        self.assertEqual(payment.gateway_fee_amount, settings.ZIBAL_IPG_FEE_MAX)
        self.assertIsNone(payment.paid_at)

    def test_wallet_order_manager_has_no_gateway_fee(self):
        order = self.make_order()
        payment = Payment.objects.create_order_payment_wallet(order=order, wallet=self.buyer_wallet, amount=1050)

        payment.refresh_from_db()
        self.assertEqual(payment.order_id, order.pk)
        self.assertEqual(payment.wallet_id, self.buyer_wallet.pk)
        self.assertEqual(payment.purpose, "ORDER_PAYMENT")
        self.assertEqual(payment.payment_method, "WALLET")
        self.assertEqual(payment.status, "PENDING")
        self.assertEqual(payment.gateway_fee_amount, 0)
        self.assertEqual(payment.total_amount, 1050)
        self.buyer_wallet.refresh_from_db()
        self.assertEqual(self.buyer_wallet.balance, 5000)

    def test_gateway_order_manager_has_order_but_no_wallet(self):
        order = self.make_order()
        payment = Payment.objects.create_order_payment_gateway(order=order, amount=1050)

        payment.refresh_from_db()
        self.assertEqual(payment.order_id, order.pk)
        self.assertIsNone(payment.wallet_id)
        self.assertEqual(payment.purpose, "ORDER_PAYMENT")
        self.assertEqual(payment.payment_method, "ONLINE_GATEWAY")
        self.assertEqual(payment.status, "PENDING")
        self.assertEqual(payment.amount, 1050)
        self.assertEqual(payment.gateway_fee_amount, settings.ZIBAL_IPG_FEE_MAX)

    def test_total_includes_gateway_fee(self):
        payment = self.make_top_up()
        self.assertEqual(payment.total_amount, 251050)

    def test_mark_paid_persists_timestamp_and_is_idempotent(self):
        payment = self.make_top_up(status="PENDING", paid_at=None)
        with patch("commerce_payments.models.timezone.now", return_value=self.now):
            payment.mark_paid()
        payment.refresh_from_db()
        self.assertEqual(payment.status, "PAID")
        self.assertEqual(payment.paid_at, self.now)
        updated_at = payment.updated_at

        with patch("commerce_payments.models.timezone.now", return_value=self.now + timedelta(days=1)):
            payment.mark_paid()
        payment.refresh_from_db()
        self.assertEqual(payment.paid_at, self.now)
        self.assertEqual(payment.updated_at, updated_at)

    def test_failed_payment_can_be_marked_paid_after_verified_recovery(self):
        payment = self.make_top_up(status="FAILED", paid_at=None)
        with patch("commerce_payments.models.timezone.now", return_value=self.now):
            payment.mark_paid()
        payment.refresh_from_db()
        self.assertEqual(payment.status, "PAID")
        self.assertEqual(payment.paid_at, self.now)

    def test_mark_failed_is_idempotent_for_pending_payment(self):
        payment = self.make_top_up(status="PENDING", paid_at=None)
        payment.mark_failed()
        payment.refresh_from_db()
        self.assertEqual(payment.status, "FAILED")
        self.assertIsNone(payment.paid_at)
        updated_at = payment.updated_at
        payment.mark_failed()
        payment.refresh_from_db()
        self.assertEqual(payment.updated_at, updated_at)

    def test_paid_payment_cannot_be_marked_failed(self):
        payment = self.make_top_up()
        updated_at = payment.updated_at
        payment.mark_failed()

        self.assertEqual(payment.status, "PAID")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "PAID")
        self.assertEqual(payment.paid_at, self.now)
        self.assertEqual(payment.updated_at, updated_at)

    def test_database_rejects_nonpositive_amounts_and_negative_fees(self):
        for values in ({"amount": 0}, {"amount": -1}, {"gateway_fee_amount": -1}):
            with self.subTest(values=values):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.make_top_up(**values)

    def test_database_rejects_invalid_purpose_method_target_combinations(self):
        order = self.make_order()
        invalid_values = (
            {"wallet": None},
            {"order": order},
            {"payment_method": "WALLET"},
            {"purpose": "ORDER_PAYMENT"},
            {"purpose": "ORDER_PAYMENT", "order": order},
            {"purpose": "ORDER_PAYMENT", "order": order, "payment_method": "WALLET", "gateway_fee_amount": 1},
            {
                "purpose": "ORDER_PAYMENT",
                "order": order,
                "payment_method": "WALLET",
                "wallet": None,
                "gateway_fee_amount": 0,
            },
            {"purpose": "UNKNOWN"},
            {"payment_method": "UNKNOWN"},
        )
        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.make_top_up(**values)

    def test_database_checks_payment_targets_on_update(self):
        payment = self.make_top_up()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.filter(pk=payment.pk).update(wallet=None)
        payment.refresh_from_db()
        self.assertEqual(payment.wallet_id, self.buyer_wallet.pk)

    def test_only_one_paid_order_payment_but_multiple_unpaid_attempts(self):
        order = self.make_order()
        first = self.make_order_payment(order)
        pending = self.make_order_payment(order, status="PENDING", paid_at=None)
        self.make_order_payment(order, status="FAILED", paid_at=None)
        with self.assertRaises(IntegrityError), transaction.atomic():
            pending.mark_paid()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_order_payment(order)
        pending.refresh_from_db()
        self.assertEqual(pending.status, "PENDING")
        self.assertEqual(Payment.objects.filter(order=order, status="PAID").get().pk, first.pk)

    def test_paid_payments_for_different_orders_and_top_ups_are_allowed(self):
        self.make_order_payment(self.make_order())
        self.make_order_payment(self.make_order())
        self.make_top_up()
        self.make_top_up()
        self.assertEqual(Payment.objects.filter(status="PAID").count(), 4)

    def test_payment_protects_wallet_and_order_from_deletion(self):
        order = self.make_order()
        Payment.objects.create_order_payment_wallet(order=order, wallet=self.buyer_wallet, amount=1050)
        for target in (order, self.buyer_wallet):
            with self.subTest(target=target.pk), self.assertRaises(ProtectedError):
                target.delete()
