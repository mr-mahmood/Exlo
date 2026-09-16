# gym_visits/tests/test_models.py
# type: ignore

from datetime import timedelta
import time
from decimal import Decimal
from unittest.mock import patch
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from commerce_orders.models import CommerceProduct, Order, OrderItem
from core.errors import APIError, GymVisitsError
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from gym_visits.models import GymVisit
from users.models import User


class GymVisitModelTestBase(TestCase):
    def setUp(self):
        self.gym = Gym.objects.create(name="Gym A")

        self.user = User.objects.create_user(
            phone_number="09120000001",
            password="x",
            first_name="A",
            last_name="B",
        )
        self.other_user = User.objects.create_user(
            phone_number="09120000002",
            password="x",
            first_name="C",
            last_name="D",
        )

        self.plan = GymMembershipPlan.objects.create_plan(
            name="Plan A",
            gym=self.gym,
            duration_months=1,
            visit_limit=30,
            price=Decimal("1000"),
        )

    def make_subscription(
        self, user, *, status=GymSubscription.Status.ACTIVE, remaining=10
    ):
        order = Order.objects.create(
            buyer=user,
            status=Order.Status.PAID,
            subtotal_amount=Decimal("0"),
            discount_amount=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("0"),
            paid_at=timezone.now(),
        )
        item = OrderItem.objects.create(
            commerce_product=self.plan.id,
            order=order,
            item_type=CommerceProduct.ProductType.GYM_MEMBERSHIP,
            item_snapshot={},
            quantity=1,
            unit_price=Decimal("0"),
            subtotal_amount=Decimal("0"),
            discount_amount=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("0"),
        )
        return GymSubscription.objects.create_subscription(
            subscriber=user,
            order_item=item,
        )


class CheckInTests(GymVisitModelTestBase):
    def test_creates_open_visit(self):
        sub = self.make_subscription(self.user)

        visit = GymVisit.objects.check_in(
            user=self.user,
            gym=self.gym,
            subscription=sub,
            method=GymVisit.Method.NFC,
        )

        self.assertEqual(visit.user_id, self.user.id)
        self.assertEqual(visit.gym_id, self.gym.id)
        self.assertEqual(visit.subscription_id, sub.id)
        self.assertEqual(visit.checked_in_method, GymVisit.Method.NFC)
        self.assertIsNone(visit.checked_out_at)

    def test_raises_when_user_already_has_open_visit(self):
        sub = self.make_subscription(self.user)
        GymVisit.objects.check_in(
            user=self.user, gym=self.gym, subscription=sub, method=GymVisit.Method.NFC
        )

        with self.assertRaises(APIError) as ctx:
            GymVisit.objects.check_in(
                user=self.user,
                gym=self.gym,
                subscription=sub,
                method=GymVisit.Method.NFC,
            )

        self.assertEqual(ctx.exception.error_code, GymVisitsError.ALREADY_CHECKED_IN[0])

    def test_integrity_error_from_constraint_maps_to_already_checked_in(self):
        sub = self.make_subscription(self.user)

        with patch("gym_visits.models.GymVisitManager.filter") as mock_filter:
            # Make the pre-check query return a fake queryset where .exists() is False.
            mock_filter.return_value.exists.return_value = False

            # Now create a real open visit directly (bypasses manager method).
            GymVisit.objects.create(
                user=self.user,
                gym=self.gym,
                subscription=sub,
                checked_in_at=timezone.now(),
                checked_in_method=GymVisit.Method.NFC,
            )

            # Restore filter for the actual insert path.
            with patch(
                "gym_visits.models.GymVisitManager.filter",
                wraps=(
                    GymVisit.objects.filter.__self__.filter
                    if hasattr(GymVisit.objects.filter, "__self__")
                    else None
                ),
            ):
                with self.assertRaises(APIError):
                    GymVisit.objects.check_in(
                        user=self.user,
                        gym=self.gym,
                        subscription=sub,
                        method=GymVisit.Method.NFC,
                    )

    def test_unique_open_per_user_constraint_blocks_second_open_visit(self):
        sub = self.make_subscription(self.user)
        GymVisit.objects.create(
            user=self.user,
            gym=self.gym,
            subscription=sub,
            checked_in_at=timezone.now(),
            checked_in_method=GymVisit.Method.NFC,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GymVisit.objects.create(
                    user=self.user,
                    gym=self.gym,
                    subscription=sub,
                    checked_in_at=timezone.now(),
                    checked_in_method=GymVisit.Method.NFC,
                )

    def test_two_users_can_be_checked_in_simultaneously(self):
        sub_a = self.make_subscription(self.user)
        sub_b = self.make_subscription(self.other_user)

        GymVisit.objects.check_in(
            user=self.user, gym=self.gym, subscription=sub_a, method=GymVisit.Method.NFC
        )
        GymVisit.objects.check_in(
            user=self.other_user,
            gym=self.gym,
            subscription=sub_b,
            method=GymVisit.Method.NFC,
        )

        self.assertEqual(
            GymVisit.objects.filter(checked_out_at__isnull=True).count(), 2
        )


class CheckInAcrossGymsTests(GymVisitModelTestBase):
    def test_second_check_in_at_different_gym_is_blocked(self):
        other_gym = Gym.objects.create(name="Gym B")

        sub = self.make_subscription(self.user)
        GymVisit.objects.check_in(
            user=self.user,
            gym=self.gym,
            subscription=sub,
            method=GymVisit.Method.NFC,
        )

        # Same subscription, different gym — the DB constraint is on user alone.
        with self.assertRaises(APIError) as ctx:
            GymVisit.objects.check_in(
                user=self.user,
                gym=other_gym,
                subscription=sub,
                method=GymVisit.Method.NFC,
            )

        self.assertEqual(ctx.exception.error_code, GymVisitsError.ALREADY_CHECKED_IN[0])


class CheckOutTests(GymVisitModelTestBase):
    def test_checks_out_open_visit(self):
        sub = self.make_subscription(self.user)
        visit = GymVisit.objects.check_in(
            user=self.user, gym=self.gym, subscription=sub, method=GymVisit.Method.NFC
        )

        visit.check_out(method=GymVisit.Method.NFC)

        visit.refresh_from_db()
        self.assertIsNotNone(visit.checked_out_at)
        self.assertEqual(visit.checked_out_method, GymVisit.Method.NFC)
        self.assertGreaterEqual(visit.checked_out_at, visit.checked_in_at)

    def test_raises_when_already_checked_out(self):
        sub = self.make_subscription(self.user)
        visit = GymVisit.objects.check_in(
            user=self.user, gym=self.gym, subscription=sub, method=GymVisit.Method.NFC
        )
        visit.check_out(method=GymVisit.Method.NFC)

        with self.assertRaises(APIError) as ctx:
            visit.check_out(method=GymVisit.Method.NFC)

        self.assertEqual(
            ctx.exception.error_code, GymVisitsError.ALREADY_CHECKED_OUT[0]
        )

    def test_raises_when_checkout_before_checkin(self):
        sub = self.make_subscription(self.user)
        visit = GymVisit.objects.check_in(
            user=self.user, gym=self.gym, subscription=sub, method=GymVisit.Method.NFC
        )

        # Force checked_in_at into the future so "now" is before it.
        GymVisit.objects.filter(pk=visit.pk).update(
            checked_in_at=timezone.now() + timedelta(hours=1)
        )
        visit.refresh_from_db()

        with self.assertRaises(APIError) as ctx:
            visit.check_out(method=GymVisit.Method.NFC)

        self.assertEqual(
            ctx.exception.error_code, GymVisitsError.INVALID_CHECKOUT_TIME[0]
        )

    def test_duration_is_none_while_open(self):
        sub = self.make_subscription(self.user)
        visit = GymVisit.objects.check_in(
            user=self.user, gym=self.gym, subscription=sub, method=GymVisit.Method.NFC
        )
        self.assertIsNone(visit.duration)

    def test_duration_is_set_after_checkout(self):
        sub = self.make_subscription(self.user)
        visit = GymVisit.objects.check_in(
            user=self.user, gym=self.gym, subscription=sub, method=GymVisit.Method.NFC
        )
        time.sleep(0.5)
        visit.check_out(method=GymVisit.Method.NFC)
        visit.refresh_from_db()
        self.assertIsNotNone(visit.duration)
        self.assertGreater(visit.duration.total_seconds(), 0)

    def test_second_check_in_after_checkout_succeeds(self):
        sub = self.make_subscription(self.user)
        first = GymVisit.objects.check_in(
            user=self.user, gym=self.gym, subscription=sub, method=GymVisit.Method.NFC
        )
        first.check_out(method=GymVisit.Method.NFC)

        second = GymVisit.objects.check_in(
            user=self.user, gym=self.gym, subscription=sub, method=GymVisit.Method.NFC
        )

        self.assertNotEqual(first.pk, second.pk)
        self.assertIsNone(second.checked_out_at)
