# gym_subscriptions/tests/test_models.py
# type: ignore

from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from commerce_orders.models import Order, OrderItem
from commerce_products.models import CommerceProduct
from core.errors import APIError, GymSubscriptionError
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User


class GymSubscriptionTestBase(TestCase):
    def create_user(self, phone="09120000000"):
        return User.objects.create_user(
            phone_number=phone,
            first_name="Test",
            last_name="User",
        )

    def create_gym(self, name="Test Gym"):
        return Gym.objects.create(
            name=name,
            province="Test Province",
            city="Test City",
            address="Test Address",
        )

    def create_plan(
        self,
        gym,
        name="Test Plan",
        duration_month=1,
        visit_limit=10,
        price=Decimal("100000"),
    ):
        return GymMembershipPlan.objects.create_plan(
            gym=gym,
            name=name,
            description="Test membership plan",
            duration_month=duration_month,
            visit_limit=visit_limit,
            price=price,
        )

    def create_order_item(self, user, plan):
        order = Order.objects.create(
            buyer=user,
            status=Order.Status.PAID,
            subtotal_amount=plan.price,
            discount_amount=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=plan.price,
            paid_at=timezone.now(),
        )

        return OrderItem.objects.create(
            commerce_product=plan.id,
            order=order,
            item_type=CommerceProduct.ProductType.GYM_MEMBERSHIP,
            item_snapshot={
                "name": plan.name,
                "price": str(plan.price),
            },
            quantity=1,
            unit_price=plan.price,
            subtotal_amount=plan.price,
            discount_amount=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=plan.price,
        )

    def create_subscription(
        self,
        user,
        plan,
        status=GymSubscription.Status.PENDING,
        remaining_visits=0,
    ):
        order_item = self.create_order_item(user, plan)

        return GymSubscription.objects.create(
            subscriber=user,
            plan=plan,
            order_item=order_item,
            status=status,
            remaining_visits=remaining_visits,
        )


class GymSubscriptionPropertyTests(GymSubscriptionTestBase):
    def test_is_expired_by_time_when_expiry_is_in_past(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() - timedelta(minutes=1)

        self.assertTrue(subscription.is_expired_by_time)
        self.assertTrue(subscription.is_expired)

    def test_is_not_expired_by_time_when_expiry_is_in_future(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() + timedelta(days=1)

        self.assertFalse(subscription.is_expired_by_time)

    def test_is_expired_by_visits_when_zero_visits(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
        )

        self.assertTrue(subscription.is_expired_by_visits)
        self.assertTrue(subscription.is_expired)

    def test_is_expired_by_visits_when_negative_visits(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
        )

        # PositiveIntegerField normally prevents negative values at validation
        # level, but the property itself should still handle <= 0.
        subscription.remaining_visits = -1

        self.assertTrue(subscription.is_expired_by_visits)

    def test_is_not_expired_when_time_and_visits_are_valid(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() + timedelta(days=1)

        self.assertFalse(subscription.is_expired)

    def test_expire_reason_is_time_when_time_expired(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() - timedelta(minutes=1)

        self.assertEqual(
            subscription.expire_reason,
            GymSubscription.EndReason.TIME,
        )

    def test_expire_reason_is_visits_when_visits_expired(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
        )

        subscription.expires_at = timezone.now() + timedelta(days=1)

        self.assertEqual(
            subscription.expire_reason,
            GymSubscription.EndReason.VISITS,
        )

    def test_expire_reason_prioritizes_time_when_both_expired(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
        )

        subscription.expires_at = timezone.now() - timedelta(minutes=1)

        self.assertEqual(
            subscription.expire_reason,
            GymSubscription.EndReason.TIME,
        )

    def test_expire_reason_is_none_when_not_expired(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() + timedelta(days=1)

        self.assertIsNone(subscription.expire_reason)

    def test_is_active_when_subscription_is_active_and_not_expired(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() + timedelta(days=1)

        self.assertTrue(subscription.is_active)

    def test_is_not_active_when_status_is_not_active(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.PENDING,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() + timedelta(days=1)

        self.assertFalse(subscription.is_active)

    def test_is_not_active_when_active_subscription_is_expired(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() - timedelta(minutes=1)

        self.assertFalse(subscription.is_active)


class GymSubscriptionActivationTests(GymSubscriptionTestBase):
    def test_activate_pending_subscription(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(
            gym,
            duration_month=3,
            visit_limit=20,
        )

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.PENDING,
            remaining_visits=0,
        )

        before = timezone.now()

        subscription.activate()

        after = timezone.now()
        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertIsNotNone(subscription.started_at)
        self.assertGreaterEqual(subscription.started_at, before)
        self.assertLessEqual(subscription.started_at, after)

        expected_expiry = subscription.started_at + relativedelta(
            months=plan.duration_month
        )

        self.assertEqual(
            subscription.expires_at,
            expected_expiry,
        )
        self.assertEqual(
            subscription.remaining_visits,
            plan.visit_limit,
        )
        self.assertIsNone(subscription.end_reason)
        self.assertIsNone(subscription.cancelled_at)

    def test_activate_non_pending_subscription_does_nothing(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        original_status = subscription.status
        original_visits = subscription.remaining_visits

        subscription.activate()

        subscription.refresh_from_db()

        self.assertEqual(subscription.status, original_status)
        self.assertEqual(subscription.remaining_visits, original_visits)

    def test_manager_activate_subscription(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(
            gym,
            duration_month=2,
            visit_limit=15,
        )

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.PENDING,
        )

        result = GymSubscription.objects.activate_subscription(subscription)

        subscription.refresh_from_db()

        self.assertEqual(result.pk, subscription.pk)
        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            subscription.remaining_visits,
            plan.visit_limit,
        )

    def test_manager_activation_rejects_existing_active_subscription(self):
        user = self.create_user()
        gym = self.create_gym()

        active_plan = self.create_plan(
            gym,
            name="Active Plan",
        )

        pending_plan = self.create_plan(
            gym,
            name="Pending Plan",
        )

        self.create_subscription(
            user,
            active_plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        pending = self.create_subscription(
            user,
            pending_plan,
            status=GymSubscription.Status.PENDING,
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.activate_subscription(pending)

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS[0],
        )

        pending.refresh_from_db()

        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )

    def test_activate_clears_previous_end_and_cancelled_fields(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.PENDING,
        )

        subscription.end_reason = GymSubscription.EndReason.CANCELLED
        subscription.cancelled_at = timezone.now()
        subscription.save(
            update_fields=[
                "end_reason",
                "cancelled_at",
            ]
        )

        subscription.activate()
        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertIsNone(subscription.end_reason)
        self.assertIsNone(subscription.cancelled_at)


class GymSubscriptionExpirationTests(GymSubscriptionTestBase):

    def test_expire_active_subscription(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expire(GymSubscription.EndReason.TIME)

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.TIME,
        )

    def test_expire_active_subscription_with_visit_reason(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=1,
        )

        subscription.expire(GymSubscription.EndReason.VISITS)

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.VISITS,
        )

    def test_expire_non_active_subscription_does_nothing(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.PENDING,
        )

        subscription.expire(GymSubscription.EndReason.TIME)

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.PENDING,
        )
        self.assertIsNone(subscription.end_reason)


class GymSubscriptionPromotionTests(GymSubscriptionTestBase):

    def test_promote_next_returns_none_when_no_pending_subscription(self):
        user = self.create_user()

        result = GymSubscription.objects.promote_next(user)

        self.assertIsNone(result)

    def test_promote_next_activates_pending_subscription(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(
            gym,
            visit_limit=20,
        )

        pending = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.PENDING,
        )

        result = GymSubscription.objects.promote_next(user)

        pending.refresh_from_db()

        self.assertEqual(result.pk, pending.pk)
        self.assertEqual(
            pending.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            pending.remaining_visits,
            plan.visit_limit,
        )

    def test_promote_next_selects_oldest_pending_subscription(self):
        user = self.create_user()
        gym = self.create_gym()

        first_plan = self.create_plan(
            gym,
            name="First Plan",
            visit_limit=10,
        )

        second_plan = self.create_plan(
            gym,
            name="Second Plan",
            visit_limit=20,
        )

        first = self.create_subscription(
            user,
            first_plan,
            status=GymSubscription.Status.PENDING,
        )

        second = self.create_subscription(
            user,
            second_plan,
            status=GymSubscription.Status.PENDING,
        )

        # Guarantee ordering regardless of timestamp resolution.
        GymSubscription.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )

        GymSubscription.objects.filter(pk=second.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )

        result = GymSubscription.objects.promote_next(user)

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertEqual(result.pk, first.pk)
        self.assertEqual(
            first.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            second.status,
            GymSubscription.Status.PENDING,
        )

    def test_promote_next_ignores_cancelled_subscription(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        cancelled = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.CANCELLED,
        )

        result = GymSubscription.objects.promote_next(user)

        self.assertIsNone(result)

        cancelled.refresh_from_db()

        self.assertEqual(
            cancelled.status,
            GymSubscription.Status.CANCELLED,
        )

    def test_promote_next_does_not_activate_when_active_subscription_exists(self):
        user = self.create_user()
        gym = self.create_gym()

        active_plan = self.create_plan(
            gym,
            name="Active Plan",
        )

        pending_plan = self.create_plan(
            gym,
            name="Pending Plan",
        )

        self.create_subscription(
            user,
            active_plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        pending = self.create_subscription(
            user,
            pending_plan,
            status=GymSubscription.Status.PENDING,
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.promote_next(user)

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS[0],
        )

        pending.refresh_from_db()

        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )


class GymSubscriptionCancellationTests(GymSubscriptionTestBase):

    def test_cancel_active_subscription(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.cancel()

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.CANCELLED,
        )
        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.CANCELLED,
        )
        self.assertIsNotNone(subscription.cancelled_at)

    def test_cancel_active_subscription_promotes_next(self):
        user = self.create_user()
        gym = self.create_gym()

        active_plan = self.create_plan(
            gym,
            name="Active Plan",
        )

        pending_plan = self.create_plan(
            gym,
            name="Pending Plan",
            visit_limit=20,
        )

        active = self.create_subscription(
            user,
            active_plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        pending = self.create_subscription(
            user,
            pending_plan,
            status=GymSubscription.Status.PENDING,
        )

        active.cancel()

        active.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            active.status,
            GymSubscription.Status.CANCELLED,
        )
        self.assertEqual(
            pending.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            pending.remaining_visits,
            pending_plan.visit_limit,
        )

    def test_cancel_pending_subscription(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.PENDING,
        )

        subscription.cancel()

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.CANCELLED,
        )
        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.CANCELLED,
        )
        self.assertIsNotNone(subscription.cancelled_at)

    def test_cancel_pending_subscription_promotes_next(self):
        user = self.create_user()
        gym = self.create_gym()

        first_plan = self.create_plan(
            gym,
            name="First Plan",
        )

        second_plan = self.create_plan(
            gym,
            name="Second Plan",
            visit_limit=20,
        )

        first = self.create_subscription(
            user,
            first_plan,
            status=GymSubscription.Status.PENDING,
        )

        second = self.create_subscription(
            user,
            second_plan,
            status=GymSubscription.Status.PENDING,
        )

        GymSubscription.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )

        GymSubscription.objects.filter(pk=second.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )

        first.cancel()

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertEqual(
            first.status,
            GymSubscription.Status.CANCELLED,
        )
        self.assertEqual(
            second.status,
            GymSubscription.Status.ACTIVE,
        )

    def test_cancel_expired_subscription_does_nothing(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.EXPIRED,
        )

        subscription.cancel()

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )

    def test_cancel_cancelled_subscription_does_nothing(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.CANCELLED,
        )

        subscription.cancelled_at = timezone.now()
        subscription.save(update_fields=["cancelled_at"])

        original_cancelled_at = subscription.cancelled_at

        subscription.cancel()

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.CANCELLED,
        )
        self.assertEqual(
            subscription.cancelled_at,
            original_cancelled_at,
        )

    def test_cancel_expired_subscription_does_not_promote_next(self):
        user = self.create_user()
        gym = self.create_gym()

        expired_plan = self.create_plan(
            gym,
            name="Expired Plan",
        )

        pending_plan = self.create_plan(
            gym,
            name="Pending Plan",
        )

        expired = self.create_subscription(
            user,
            expired_plan,
            status=GymSubscription.Status.EXPIRED,
        )

        pending = self.create_subscription(
            user,
            pending_plan,
            status=GymSubscription.Status.PENDING,
        )

        expired.cancel()

        expired.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            expired.status,
            GymSubscription.Status.EXPIRED,
        )

        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )


class GymSubscriptionCheckInTests(GymSubscriptionTestBase):

    def test_check_in_without_active_subscription(self):
        user = self.create_user()
        gym = self.create_gym()

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.check_in(user, gym)

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

    def test_check_in_successfully_consumes_one_visit(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(
            gym,
            visit_limit=10,
        )

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() + timedelta(days=10)
        subscription.save(update_fields=["expires_at"])

        result = GymSubscription.objects.check_in(user, gym)

        subscription.refresh_from_db()

        self.assertEqual(result.pk, subscription.pk)
        self.assertEqual(
            subscription.remaining_visits,
            9,
        )
        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )

    def test_check_in_wrong_gym_raises_error(self):
        user = self.create_user()
        gym = self.create_gym(name="Correct Gym")
        wrong_gym = self.create_gym(name="Wrong Gym")

        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() + timedelta(days=10)
        subscription.save(update_fields=["expires_at"])

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.check_in(user, wrong_gym)

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.WRONG_GYM[0],
        )

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            subscription.remaining_visits,
            10,
        )

    def test_check_in_expired_by_time_promotes_next_subscription(self):
        user = self.create_user()
        gym = self.create_gym()

        expired_plan = self.create_plan(
            gym,
            name="Expired Plan",
        )

        next_plan = self.create_plan(
            gym,
            name="Next Plan",
            visit_limit=20,
        )

        expired = self.create_subscription(
            user,
            expired_plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        expired.expires_at = timezone.now() - timedelta(minutes=1)
        expired.save(update_fields=["expires_at"])

        pending = self.create_subscription(
            user,
            next_plan,
            status=GymSubscription.Status.PENDING,
        )

        result = GymSubscription.objects.check_in(user, gym)

        expired.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            expired.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            expired.end_reason,
            GymSubscription.EndReason.TIME,
        )

        self.assertEqual(
            pending.status,
            GymSubscription.Status.ACTIVE,
        )

        self.assertEqual(
            pending.remaining_visits,
            next_plan.visit_limit - 1,
        )

        self.assertEqual(
            result.pk,
            pending.pk,
        )

    def test_check_in_expired_by_visits_promotes_next_subscription(self):
        user = self.create_user()
        gym = self.create_gym()

        expired_plan = self.create_plan(
            gym,
            name="Expired Plan",
        )

        next_plan = self.create_plan(
            gym,
            name="Next Plan",
            visit_limit=20,
        )

        expired = self.create_subscription(
            user,
            expired_plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
        )

        expired.expires_at = timezone.now() + timedelta(days=10)
        expired.save(update_fields=["expires_at"])

        pending = self.create_subscription(
            user,
            next_plan,
            status=GymSubscription.Status.PENDING,
        )

        result = GymSubscription.objects.check_in(user, gym)

        expired.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            expired.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            expired.end_reason,
            GymSubscription.EndReason.VISITS,
        )

        self.assertEqual(
            pending.status,
            GymSubscription.Status.ACTIVE,
        )

        self.assertEqual(
            pending.remaining_visits,
            next_plan.visit_limit - 1,
        )

        self.assertEqual(
            result.pk,
            pending.pk,
        )

    def test_check_in_expired_subscription_without_pending_raises_error_and_persists_expiration(
        self,
    ):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() - timedelta(minutes=1)
        subscription.save(update_fields=["expires_at"])

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.check_in(user, gym)

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.TIME,
        )

    def test_check_in_last_visit_expires_subscription(self):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(
            gym,
            visit_limit=1,
        )

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=1,
        )

        subscription.expires_at = timezone.now() + timedelta(days=10)
        subscription.save(update_fields=["expires_at"])

        result = GymSubscription.objects.check_in(user, gym)

        subscription.refresh_from_db()

        self.assertEqual(
            result.pk,
            subscription.pk,
        )
        self.assertEqual(
            subscription.remaining_visits,
            0,
        )
        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.VISITS,
        )

    def test_check_in_last_visit_promotes_next_subscription(self):
        user = self.create_user()
        gym = self.create_gym()

        first_plan = self.create_plan(
            gym,
            name="First Plan",
            visit_limit=1,
        )

        next_plan = self.create_plan(
            gym,
            name="Next Plan",
            visit_limit=20,
        )

        first = self.create_subscription(
            user,
            first_plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=1,
        )

        first.expires_at = timezone.now() + timedelta(days=10)
        first.save(update_fields=["expires_at"])

        next_subscription = self.create_subscription(
            user,
            next_plan,
            status=GymSubscription.Status.PENDING,
        )

        GymSubscription.objects.check_in(user, gym)

        first.refresh_from_db()
        next_subscription.refresh_from_db()

        self.assertEqual(
            first.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            first.end_reason,
            GymSubscription.EndReason.VISITS,
        )

        self.assertEqual(
            next_subscription.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            next_subscription.remaining_visits,
            next_plan.visit_limit,
        )

    def test_check_in_expired_subscription_wrong_gym_persists_expiration(self):
        user = self.create_user()
        gym = self.create_gym(name="Correct Gym")
        wrong_gym = self.create_gym(name="Wrong Gym")

        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() - timedelta(minutes=1)
        subscription.save(update_fields=["expires_at"])

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.check_in(user, wrong_gym)

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, GymSubscription.Status.EXPIRED)
        self.assertEqual(subscription.end_reason, GymSubscription.EndReason.TIME)

    def test_check_in_expired_subscription_promotes_before_error_when_promoted_subscription_belongs_to_wrong_gym(
        self,
    ):
        user = self.create_user()

        gym_a = self.create_gym(name="Gym A")
        gym_b = self.create_gym(name="Gym B")

        expired_plan = self.create_plan(
            gym_a,
            name="Expired Plan",
        )

        next_plan = self.create_plan(
            gym_b,
            name="Next Plan",
            visit_limit=20,
        )

        expired = self.create_subscription(
            user,
            expired_plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        expired.expires_at = timezone.now() - timedelta(minutes=1)
        expired.save(update_fields=["expires_at"])

        pending = self.create_subscription(
            user,
            next_plan,
            status=GymSubscription.Status.PENDING,
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.check_in(user, gym_a)

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.WRONG_GYM[0],
        )

        expired.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            expired.status,
            GymSubscription.Status.EXPIRED,
        )

        self.assertEqual(
            pending.status,
            GymSubscription.Status.ACTIVE,
        )

    def test_check_in_visit_expired_without_pending_raises_and_persists_expiration(
        self,
    ):
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
        )

        subscription.expires_at = timezone.now() + timedelta(days=10)
        subscription.save(update_fields=["expires_at"])

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.check_in(user, gym)

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )

        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.VISITS,
        )


class GymSubscriptionConstraintTests(GymSubscriptionTestBase):

    def test_only_one_active_subscription_per_user(self):
        user = self.create_user()
        gym = self.create_gym()

        first_plan = self.create_plan(
            gym,
            name="First Plan",
        )

        second_plan = self.create_plan(
            gym,
            name="Second Plan",
        )

        self.create_subscription(
            user,
            first_plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        with self.assertRaises(IntegrityError):
            self.create_subscription(
                user,
                second_plan,
                status=GymSubscription.Status.ACTIVE,
                remaining_visits=10,
            )

    def test_multiple_pending_subscriptions_are_allowed(self):
        user = self.create_user()
        gym = self.create_gym()

        first_plan = self.create_plan(
            gym,
            name="First Plan",
        )

        second_plan = self.create_plan(
            gym,
            name="Second Plan",
        )

        first = self.create_subscription(
            user,
            first_plan,
            status=GymSubscription.Status.PENDING,
        )

        second = self.create_subscription(
            user,
            second_plan,
            status=GymSubscription.Status.PENDING,
        )

        self.assertEqual(
            GymSubscription.objects.filter(
                subscriber=user,
                status=GymSubscription.Status.PENDING,
            ).count(),
            2,
        )

        self.assertIsNotNone(first.pk)
        self.assertIsNotNone(second.pk)

    def test_multiple_expired_subscriptions_are_allowed(self):
        user = self.create_user()
        gym = self.create_gym()

        first_plan = self.create_plan(
            gym,
            name="First Plan",
        )

        second_plan = self.create_plan(
            gym,
            name="Second Plan",
        )

        first = self.create_subscription(
            user,
            first_plan,
            status=GymSubscription.Status.EXPIRED,
        )

        second = self.create_subscription(
            user,
            second_plan,
            status=GymSubscription.Status.EXPIRED,
        )

        self.assertEqual(
            GymSubscription.objects.filter(
                subscriber=user,
                status=GymSubscription.Status.EXPIRED,
            ).count(),
            2,
        )

        self.assertIsNotNone(first.pk)
        self.assertIsNotNone(second.pk)


class GymSubscriptionTransactionTests(GymSubscriptionTestBase):

    def test_expiration_is_committed_before_no_active_error(self):
        """
        check_in() intentionally raises after transaction.atomic()
        so expiration is not rolled back.
        """
        user = self.create_user()
        gym = self.create_gym()
        plan = self.create_plan(gym)

        subscription = self.create_subscription(
            user,
            plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        subscription.expires_at = timezone.now() - timedelta(minutes=1)
        subscription.save(update_fields=["expires_at"])

        with self.assertRaises(APIError):
            GymSubscription.objects.check_in(user, gym)

        self.assertEqual(
            GymSubscription.objects.get(pk=subscription.pk).status,
            GymSubscription.Status.EXPIRED,
        )

    def test_promotion_is_committed_before_wrong_gym_error(self):
        user = self.create_user()

        gym_a = self.create_gym(name="Gym A")
        gym_b = self.create_gym(name="Gym B")

        expired_plan = self.create_plan(
            gym_a,
            name="Expired Plan",
        )

        next_plan = self.create_plan(
            gym_b,
            name="Next Plan",
            visit_limit=20,
        )

        expired = self.create_subscription(
            user,
            expired_plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )

        expired.expires_at = timezone.now() - timedelta(minutes=1)
        expired.save(update_fields=["expires_at"])

        pending = self.create_subscription(
            user,
            next_plan,
            status=GymSubscription.Status.PENDING,
        )

        with self.assertRaises(APIError):
            GymSubscription.objects.check_in(user, gym_a)

        expired.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            expired.status,
            GymSubscription.Status.EXPIRED,
        )

        self.assertEqual(
            pending.status,
            GymSubscription.Status.ACTIVE,
        )
