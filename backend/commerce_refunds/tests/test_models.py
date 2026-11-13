from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from commerce_payments.models import Payment
from commerce_refunds.models import Refund
from commerce_wallet.models import Wallet
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from users.models import User


class RefundModelTests(TestCase):
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

    def test_top_up_refund_manager_excludes_gateway_fee_and_does_not_credit_wallet(self):
        payment = self.make_top_up()
        refund = Refund.objects.create_wallet_top_up_refund(payment)

        refund.refresh_from_db()
        self.assertEqual(refund.payment_id, payment.pk)
        self.assertEqual(payment.refund, refund)
        self.assertEqual(refund.amount, 1050)
        self.assertEqual(refund.status, "PENDING")
        self.assertIsNone(refund.refunded_at)
        self.buyer_wallet.refresh_from_db()
        self.assertEqual(self.buyer_wallet.balance, 5000)

    def test_completion_persists_timestamp_and_is_idempotent(self):
        refund = Refund.objects.create_wallet_top_up_refund(self.make_top_up())
        with patch("commerce_refunds.models.timezone.now", return_value=self.now):
            refund.mark_completed()
        refund.refresh_from_db()
        self.assertEqual(refund.status, "COMPLETED")
        self.assertEqual(refund.refunded_at, self.now)
        updated_at = refund.updated_at

        with patch("commerce_refunds.models.timezone.now", return_value=self.now + timedelta(days=1)):
            refund.mark_completed()
        refund.refresh_from_db()
        self.assertEqual(refund.refunded_at, self.now)
        self.assertEqual(refund.updated_at, updated_at)

    def test_only_one_refund_per_payment(self):
        payment = self.make_top_up()
        Refund.objects.create_wallet_top_up_refund(payment)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Refund.objects.create_wallet_top_up_refund(payment)
        self.assertEqual(Refund.objects.filter(payment=payment).count(), 1)

    def test_database_rejects_nonpositive_amount_on_insert_and_update(self):
        payment = self.make_top_up()
        for amount in (0, -1):
            with self.subTest(amount=amount):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Refund.objects.create(payment=payment, amount=amount)
        refund = Refund.objects.create_wallet_top_up_refund(payment)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Refund.objects.filter(pk=refund.pk).update(amount=0)
        refund.refresh_from_db()
        self.assertEqual(refund.amount, 1050)

    def test_refund_protects_payment_from_deletion(self):
        payment = self.make_top_up()
        Refund.objects.create_wallet_top_up_refund(payment)
        with self.assertRaises(ProtectedError):
            payment.delete()
