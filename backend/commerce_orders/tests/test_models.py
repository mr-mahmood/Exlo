from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from commerce_orders.models import Order
from commerce_wallet.models import Wallet
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User


class OrderModelTests(TestCase):
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

    def make_subscription(self, order, **values):
        subscription = GymSubscription.objects.create(
            **{
                "order": order,
                "subscriber": order.buyer,
                "plan": self.plan,
                "status": GymSubscription.Status.EXPIRED,
                "initial_visits": 30,
                "remaining_visits": 30,
                "duration_months": 1,
                "started_at": self.now - timedelta(days=31),
                "expires_at": self.now - timedelta(days=1),
                **values,
            }
        )
        GymSubscription.objects.filter(pk=subscription.pk).update(created_at=self.now - timedelta(days=31))
        subscription.refresh_from_db()
        return subscription

    def test_total_subtracts_discount_and_adds_tax(self):
        order = self.make_order()
        self.assertEqual(order.total_amount, 1050)
        self.assertEqual(order.product_snapshot, {"name": "Monthly membership", "visit_limit": 30})

    def test_minimum_seller_revenue_is_one_rial(self):
        order = self.make_order(subtotal_amount=200, discount_amount=199, tax_amount=0)
        self.assertEqual(order.total_amount, 1)

    def test_database_rejects_equal_or_excessive_discount_and_negative_amounts(self):
        invalid_values = (
            {"subtotal_amount": 0, "discount_amount": 0},
            {"discount_amount": 1200},
            {"discount_amount": 1201},
            {"subtotal_amount": -1},
            {"discount_amount": -1},
            {"tax_amount": -1},
        )
        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.make_order(**values)

    def test_database_checks_discount_on_update(self):
        order = self.make_order()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.filter(pk=order.pk).update(discount_amount=1200)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, 200)

    def test_release_requires_successful_order_at_database_level(self):
        for status in ("PENDING", "FAILED"):
            with self.subTest(status=status):
                order = self.make_order(status=status)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Order.objects.filter(pk=order.pk).update(settlement_status="RELEASED")
                order.refresh_from_db()
                self.assertEqual(order.settlement_status, "HELD")

    def test_held_settlement_can_be_released_or_voided_once(self):
        for method, expected in (("mark_settlement_released", "RELEASED"), ("mark_settlement_voided", "VOIDED")):
            with self.subTest(method=method):
                order = self.make_order()
                getattr(order, method)()
                order.refresh_from_db()
                self.assertEqual(order.settlement_status, expected)
                self.assertEqual(order.status, "SUCCEEDED")
                updated_at = order.updated_at
                order.mark_settlement_released()
                order.mark_settlement_voided()
                order.refresh_from_db()
                self.assertEqual(order.settlement_status, expected)
                self.assertEqual(order.updated_at, updated_at)

    def test_refundability_uses_actual_membership_and_48_hour_boundary(self):
        order = self.make_order()
        subscription = self.make_subscription(
            order,
            status="ACTIVE",
            started_at=self.now,
            expires_at=self.now + timedelta(days=30),
        )
        created_at = self.now - timedelta(hours=48)
        GymSubscription.objects.filter(pk=subscription.pk).update(created_at=created_at)
        for now, expected in (
            (created_at - timedelta(microseconds=1), False),
            (created_at, True),
            (self.now - timedelta(microseconds=1), True),
            (self.now, False),
            (self.now + timedelta(microseconds=1), False),
        ):
            with self.subTest(now=now):
                with patch("gym_subscriptions.models.timezone.now", return_value=now):
                    self.assertEqual(Order.objects.get(pk=order.pk).is_refundable, expected)

    def test_used_cancelled_or_expired_membership_is_not_refundable(self):
        order = self.make_order()
        subscription = self.make_subscription(order)
        for status, remaining_visits, expected in (
            ("PENDING", 30, True),
            ("ACTIVE", 30, True),
            ("ACTIVE", 29, False),
            ("CANCELLED", 30, False),
            ("EXPIRED", 30, False),
        ):
            with self.subTest(status=status, remaining_visits=remaining_visits):
                GymSubscription.objects.filter(pk=subscription.pk).update(
                    created_at=self.now - timedelta(hours=1), status=status, remaining_visits=remaining_visits
                )
                with patch("gym_subscriptions.models.timezone.now", return_value=self.now):
                    self.assertEqual(Order.objects.get(pk=order.pk).is_refundable, expected)

    def test_cancel_purchased_product_persists_membership_cancellation_only_once(self):
        order = self.make_order()
        subscription = self.make_subscription(
            order,
            status="ACTIVE",
            started_at=self.now - timedelta(days=1),
            expires_at=self.now + timedelta(days=29),
        )
        with patch("gym_subscriptions.models.timezone.now", return_value=self.now):
            order.cancel_purchased_product()
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, "CANCELLED")
        self.assertEqual(subscription.end_reason, "CANCELLED")
        self.assertEqual(subscription.cancelled_at, self.now)
        updated_at = subscription.updated_at

        with patch("gym_subscriptions.models.timezone.now", return_value=self.now + timedelta(days=1)):
            Order.objects.get(pk=order.pk).cancel_purchased_product()
        subscription.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(subscription.cancelled_at, self.now)
        self.assertEqual(subscription.updated_at, updated_at)
        self.assertEqual(order.status, "SUCCEEDED")
        self.assertEqual(order.settlement_status, "HELD")

    def test_order_protects_product_buyer_and_seller(self):
        self.make_order()
        product = self.plan.id
        # Remove other protected references so only the order can block deletion.
        self.plan.delete()
        self.buyer_wallet.delete()
        self.seller_wallet.delete()
        for target in (product, self.buyer, self.seller):
            with self.subTest(target=target.pk), self.assertRaises(ProtectedError):
                target.delete()
