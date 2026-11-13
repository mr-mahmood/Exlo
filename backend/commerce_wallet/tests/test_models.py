from datetime import datetime, timezone
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from commerce_wallet.models import Wallet
from core.errors import APIError, WalletError
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from users.models import User


class WalletModelTests(TestCase):
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

    def test_credit_persists_exact_amount_and_preserves_other_wallets(self):
        self.buyer_wallet.credit(1050)

        self.buyer_wallet.refresh_from_db()
        self.other_wallet.refresh_from_db()
        self.assertEqual(self.buyer_wallet.balance, 6050)
        self.assertEqual(self.other_wallet.balance, 900)

    def test_debit_persists_exact_amount(self):
        self.buyer_wallet.debit(1050)

        self.buyer_wallet.refresh_from_db()
        self.assertEqual(self.buyer_wallet.balance, 3950)

    def test_debit_entire_balance_leaves_zero(self):
        self.buyer_wallet.debit(5000)

        self.buyer_wallet.refresh_from_db()
        self.assertEqual(self.buyer_wallet.balance, 0)

    def test_insufficient_balance_changes_nothing(self):
        original_updated_at = self.buyer_wallet.updated_at
        with self.assertRaises(APIError) as caught:
            self.buyer_wallet.debit(5001)

        self.assertEqual(caught.exception.error_code, WalletError.BALANCE_NOT_ENOUGH[0])
        self.assertEqual(self.buyer_wallet.balance, 5000)
        self.buyer_wallet.refresh_from_db()
        self.assertEqual(self.buyer_wallet.balance, 5000)
        self.assertEqual(self.buyer_wallet.updated_at, original_updated_at)

    def test_nonpositive_amounts_are_ignored_without_mutating_wallet(self):
        invalid_amounts = (0, -1, -5001, 0.0, -1.5, Decimal("0"), Decimal("-1.5"))
        for method in ("credit", "debit"):
            for amount in invalid_amounts:
                with self.subTest(method=method, amount=amount):
                    self.buyer_wallet.refresh_from_db()
                    original_updated_at = self.buyer_wallet.updated_at
                    with self.assertNumQueries(0):
                        getattr(self.buyer_wallet, method)(amount)
                    self.assertEqual(self.buyer_wallet.balance, 5000)
                    self.buyer_wallet.refresh_from_db()
                    self.assertEqual(self.buyer_wallet.balance, 5000)
                    self.assertEqual(self.buyer_wallet.updated_at, original_updated_at)

    def test_database_rejects_negative_balance(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Wallet.objects.filter(pk=self.buyer_wallet.pk).update(balance=-1)
        self.buyer_wallet.refresh_from_db()
        self.assertEqual(self.buyer_wallet.balance, 5000)

    def test_owner_can_have_only_one_wallet(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Wallet.objects.create(owner=self.buyer)

    def test_wallet_protects_owner_from_deletion(self):
        with self.assertRaises(ProtectedError):
            self.buyer.delete()
