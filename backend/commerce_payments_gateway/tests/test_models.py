from datetime import datetime, timezone

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from commerce_payments.models import Payment
from commerce_payments_gateway.models import PaymentGateway
from commerce_wallet.models import Wallet
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from users.models import User


class PaymentGatewayModelTests(TestCase):
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

    def test_verification_persists_receipt_without_changing_payment_or_wallet(self):
        payment = self.make_top_up(status="PENDING", paid_at=None)
        gateway = PaymentGateway.objects.create(payment=payment, track_id=123456)
        created_at = gateway.created_at
        gateway.mark_verified(ref_num="receipt-123", card_number="603799******1234")
        gateway.refresh_from_db()

        self.assertEqual(gateway.ref_num, "receipt-123")
        self.assertEqual(gateway.card_number, "603799******1234")
        self.assertEqual(gateway.track_id, 123456)
        self.assertEqual(gateway.payment_id, payment.pk)
        self.assertEqual(gateway.created_at, created_at)
        payment.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.assertEqual(payment.status, "PENDING")
        self.assertEqual(self.buyer_wallet.balance, 5000)

    def test_track_id_is_unique_across_payments(self):
        PaymentGateway.objects.create(payment=self.make_top_up(), track_id=123456)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentGateway.objects.create(payment=self.make_top_up(), track_id=123456)

    def test_each_payment_has_only_one_gateway_record(self):
        payment = self.make_top_up()
        gateway = PaymentGateway.objects.create(payment=payment, track_id=123456)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentGateway.objects.create(payment=payment, track_id=654321)
        payment.refresh_from_db()
        self.assertEqual(payment.gateway_payment, gateway)

    def test_gateway_record_protects_payment_from_deletion(self):
        payment = self.make_top_up()
        PaymentGateway.objects.create(payment=payment, track_id=123456)
        with self.assertRaises(ProtectedError):
            payment.delete()
