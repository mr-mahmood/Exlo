# gym_subscriptions/tests/test_models.py


from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from dateutil.relativedelta import relativedelta
from django.core.cache import cache
from django.db import IntegrityError, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from commerce_orders.models import Order
from core.errors import APIError, GymSubscriptionError
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User
from django.db import transaction


class GymSubscriptionTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="09120000001",
            password="testpassword123",
        )

        self.user_2 = User.objects.create_user(
            phone_number="09120000002",
            password="testpassword123",
        )

        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Tehran",
            city="Tehran",
            address="Test Address",
        )

        self.gym_2 = Gym.objects.create(
            name="Second Gym",
            province="Tehran",
            city="Tehran",
            address="Second Address",
        )

        self.plan = GymMembershipPlan.objects.create_plan(
            name="Monthly Plan",
            gym=self.gym,
            duration_months=1,
            visit_limit=30,
            price=10000,
        )

        self.plan_2 = GymMembershipPlan.objects.create_plan(
            name="Three Month Plan",
            gym=self.gym,
            duration_months=3,
            visit_limit=60,
            price=20000,
        )

        self.plan_3 = GymMembershipPlan.objects.create_plan(
            name="Second Gym Plan",
            gym=self.gym_2,
            duration_months=1,
            visit_limit=20,
            price=30000,
        )

    def create_order(self, user, plan):
        order = Order.objects.create(
            buyer=user,
            status=Order.Status.SUCCEEDED,
            subtotal_amount=100000,
            discount_amount=0,
            tax_amount=0,
            total_amount=100000,
            succeeded_at=timezone.now(),
            commerce_product=plan.id,
            product_snapshot={
                "id": str(plan.pk),
                "name": plan.name,
                "gym_id": str(plan.gym_id),
                "duration_months": plan.duration_months,
                "visit_limit": plan.visit_limit,
            },
        )

        return order

    def create_subscription(self, user, plan):
        order = self.create_order(user, plan)

        return GymSubscription.objects.create_subscription(
            subscriber=user,
            order=order,
        )

    def create_raw_subscription(
        self,
        user,
        plan,
        *,
        status=GymSubscription.Status.PENDING,
        remaining_visits=None,
        duration_months=None,
        started_at=None,
        expires_at=None,
        end_reason=None,
        cancelled_at=None,
        created_at=None,
    ):
        order = self.create_order(user, plan)

        # New design: remaining_visits and duration_months are set at creation
        # from the plan. Default to plan values unless explicitly overridden.
        if remaining_visits is None:
            remaining_visits = plan.visit_limit
        if duration_months is None:
            duration_months = plan.duration_months

        subscription = GymSubscription.objects.create(
            subscriber=user,
            plan=plan,
            order=order,
            status=status,
            initial_visits=plan.visit_limit,
            remaining_visits=remaining_visits,
            duration_months=duration_months,
            started_at=started_at,
            expires_at=expires_at,
            end_reason=end_reason,
            cancelled_at=cancelled_at,
        )

        if created_at is not None:
            GymSubscription.objects.filter(pk=subscription.pk).update(created_at=created_at)
            subscription.refresh_from_db()

        return subscription


class GymSubscriptionPropertyTests(GymSubscriptionTestBase):
    def test_is_expired_by_time_when_expires_at_is_in_past(self):
        subscription: GymSubscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertTrue(subscription.is_expired)
        self.assertTrue(subscription.is_expired_by_time)
        self.assertTrue(subscription.expire_reason == GymSubscription.EndReason.TIME)

    def test_is_not_expired_by_time_when_expires_at_is_in_future(self):
        subscription:GymSubscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=1),
        )

        self.assertFalse(subscription.is_expired)
        self.assertFalse(subscription.is_expired_by_time)
        self.assertFalse(subscription.expire_reason == GymSubscription.EndReason.TIME)

    def test_is_expired_by_visits_when_remaining_visits_is_zero(self):
        subscription: GymSubscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
            expires_at=timezone.now() + timedelta(days=1),
        )

        self.assertTrue(subscription.is_expired)
        self.assertTrue(subscription.is_expired_by_visits)
        self.assertTrue(subscription.expire_reason == GymSubscription.EndReason.VISITS)

    def test_is_expired_by_visits_when_remaining_visits_is_zero_even_if_time_is_valid(self):
        subscription: GymSubscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
            expires_at=timezone.now() + timedelta(days=30),
        )

        self.assertTrue(subscription.is_expired)
        self.assertTrue(subscription.is_expired_by_visits)
        self.assertTrue(subscription.expire_reason == GymSubscription.EndReason.VISITS)

    def test_is_not_expired_when_time_and_visits_are_valid(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=30),
        )

        self.assertFalse(subscription.is_expired)

    def test_expire_reason_is_time_when_time_expired(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertEqual(
            subscription.expire_reason,
            GymSubscription.EndReason.TIME,
        )

    def test_expire_reason_is_visits_when_visits_exhausted(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
            expires_at=timezone.now() + timedelta(days=30),
        )

        self.assertEqual(
            subscription.expire_reason,
            GymSubscription.EndReason.VISITS,
        )

    def test_expire_reason_is_time_when_both_time_and_visits_are_expired(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertEqual(
            subscription.expire_reason,
            GymSubscription.EndReason.TIME,
        )

    def test_expire_reason_is_none_when_subscription_is_not_expired(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=30),
        )

        self.assertIsNone(subscription.expire_reason)

    def test_is_active_for_valid_active_subscription(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=30),
        )

        self.assertTrue(subscription.is_active)

    def test_is_not_active_when_status_is_pending(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.PENDING,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=30),
        )

        self.assertFalse(subscription.is_active)

    def test_is_not_active_when_status_is_expired(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.EXPIRED,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=30),
        )

        self.assertFalse(subscription.is_active)

    def test_is_not_active_when_status_is_cancelled(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.CANCELLED,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=30),
        )

        self.assertFalse(subscription.is_active)

    def test_is_not_active_when_active_but_expired(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertFalse(subscription.is_active)


class GymSubscriptionRefundTests(GymSubscriptionTestBase):
    def test_refund_requires_unused_visits_and_open_status(self):
        for status in GymSubscription.Status.values:
            for remaining in (30, 29):
                with self.subTest(status=status, remaining=remaining):
                    subscription = self.create_raw_subscription(
                        self.user, self.plan, status=status,
                        remaining_visits=remaining,
                    )
                    self.assertEqual(
                        subscription.is_refundable,
                        status in ("PENDING", "ACTIVE") and remaining == 30,
                    )
                    subscription.delete()

    def test_refund_window_boundaries(self):
        subscription = self.create_raw_subscription(self.user, self.plan)
        created = subscription.created_at
        for offset, expected in (
            (timedelta(microseconds=-1), False),
            (timedelta(0), True),
            (timedelta(hours=48, microseconds=-1), True),
            (timedelta(hours=48), False),
            (timedelta(hours=49), False),
        ):
            with self.subTest(offset=offset):
                with patch("gym_subscriptions.models.timezone.now", return_value=created + offset):
                    self.assertEqual(subscription.is_refundable, expected)

    def test_creation_snapshots_visits_independently_of_later_plan_changes(self):
        subscription = self.create_subscription(self.user, self.plan)
        self.plan.visit_limit = 60
        self.plan.save(update_fields=["visit_limit"])
        subscription.refresh_from_db()
        self.assertEqual(subscription.initial_visits, 30)
        self.assertEqual(subscription.remaining_visits, 30)
        self.assertTrue(subscription.is_refundable)

    def test_consuming_visit_preserves_snapshot_and_removes_refund_eligibility(self):
        subscription = self.create_subscription(self.user, self.plan)
        GymSubscription.objects.consume_visit(self.user, self.gym)
        subscription.refresh_from_db()
        self.assertEqual(subscription.initial_visits, 30)
        self.assertEqual(subscription.remaining_visits, 29)
        self.assertFalse(subscription.is_refundable)

    def test_pending_snapshot_survives_activation_after_plan_changes(self):
        active = self.create_subscription(self.user, self.plan)
        active.remaining_visits = 2
        active.save(update_fields=["remaining_visits"])
        pending = self.create_subscription(self.user, self.plan_2)
        pending.refresh_from_db()
        self.assertEqual(pending.initial_visits, 60)
        self.assertTrue(pending.is_refundable)
        self.plan_2.visit_limit = 90
        self.plan_2.save(update_fields=["visit_limit"])
        GymSubscription.objects.cancel_subscription(active)
        pending.refresh_from_db()
        self.assertEqual(pending.status, "ACTIVE")
        self.assertEqual(pending.initial_visits, 60)
        self.assertEqual(pending.remaining_visits, 60)
        self.assertTrue(pending.is_refundable)


class GymSubscriptionCreationTests(GymSubscriptionTestBase):
    def test_other_gym_subscription_activates_independently(self):
        first = self.create_subscription(self.user, self.plan)
        second = self.create_subscription(self.user, self.plan_3)

        first.refresh_from_db()
        self.assertEqual(first.status, GymSubscription.Status.ACTIVE)
        self.assertEqual(second.status, GymSubscription.Status.ACTIVE)

    def test_early_same_gym_renewal_is_rejected(self):
        active = self.create_subscription(self.user, self.plan)
        with self.assertRaises(APIError) as raised:
            self.create_subscription(self.user, self.plan_2)

        self.assertEqual(raised.exception.error_code, GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS[0])
        self.assertEqual(active.status, GymSubscription.Status.ACTIVE)
        self.assertEqual(GymSubscription.objects.filter(subscriber=self.user).count(), 1)

    def test_renewal_allowed_with_seven_days_remaining(self):
        active = self.create_subscription(self.user, self.plan)
        active.expires_at = timezone.now() + timedelta(days=7)
        active.save(update_fields=["expires_at"])

        renewal = self.create_subscription(self.user, self.plan_2)

        self.assertEqual(renewal.status, GymSubscription.Status.PENDING)
        self.assertIsNone(renewal.started_at)
        self.assertEqual(renewal.remaining_visits, self.plan_2.visit_limit)

    def test_renewal_allowed_with_two_visits_remaining(self):
        active = self.create_subscription(self.user, self.plan)
        active.remaining_visits = 2
        active.save(update_fields=["remaining_visits"])

        renewal = self.create_subscription(self.user, self.plan)

        self.assertEqual(renewal.status, GymSubscription.Status.PENDING)
        self.assertEqual(renewal.remaining_visits, self.plan.visit_limit)

    def test_create_subscription_activates_when_user_has_no_active_subscription(
        self,
    ):
        subscription = self.create_subscription(self.user, self.plan)

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertIsNotNone(subscription.started_at)
        self.assertIsNotNone(subscription.expires_at)
        self.assertEqual(
            subscription.remaining_visits,
            self.plan.visit_limit,
        )

    def test_create_subscription_copies_duration_months_from_plan(self):
        subscription = self.create_subscription(self.user, self.plan_2)

        self.assertEqual(
            subscription.duration_months,
            self.plan_2.duration_months,
        )

    def test_create_subscription_copies_visit_limit_from_plan(self):
        subscription = self.create_subscription(self.user, self.plan_2)

        self.assertEqual(
            subscription.remaining_visits,
            self.plan_2.visit_limit,
        )

    def test_create_pending_subscription_copies_duration_and_visits_from_plan(
        self,
    ):
        # Create an active subscription first so the next one stays pending
        active = self.create_subscription(self.user, self.plan)
        active.remaining_visits = 2
        active.save(update_fields=["remaining_visits"])

        pending = self.create_subscription(self.user, self.plan_2)

        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )
        self.assertEqual(
            pending.duration_months,
            self.plan_2.duration_months,
        )
        self.assertEqual(
            pending.remaining_visits,
            self.plan_2.visit_limit,
        )

    def test_create_subscription_sets_correct_expiration(self):
        before = timezone.now()

        subscription = self.create_subscription(self.user, self.plan)

        after = timezone.now()

        expected_min = before + relativedelta(months=self.plan.duration_months)
        expected_max = after + relativedelta(months=self.plan.duration_months)

        self.assertGreaterEqual(subscription.expires_at, expected_min)
        self.assertLessEqual(subscription.expires_at, expected_max)

    def test_create_subscription_sets_started_at(self):
        before = timezone.now()

        subscription = self.create_subscription(self.user, self.plan)

        after = timezone.now()

        self.assertIsNotNone(subscription.started_at)
        self.assertGreaterEqual(subscription.started_at, before)
        self.assertLessEqual(subscription.started_at, after)

    def test_create_subscription_links_order(self):
        subscription = self.create_subscription(self.user, self.plan)

        self.assertIsNotNone(subscription.order_id)
        self.assertEqual(
            subscription.order.buyer_id,
            self.user.id,
        )
        self.assertEqual(subscription.plan_id, self.plan.pk)
        self.assertEqual(subscription.subscriber_id, self.user.id)

    def test_create_subscription_is_pending_when_active_subscription_exists(
        self,
    ):
        active = self.create_subscription(self.user, self.plan)
        active.remaining_visits = 2
        active.save(update_fields=["remaining_visits"])

        pending = self.create_subscription(self.user, self.plan_2)

        active.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            active.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )

    def test_create_subscription_does_not_change_existing_active_subscription(
        self,
    ):
        active = self.create_subscription(self.user, self.plan)
        active.remaining_visits = 2
        active.save(update_fields=["remaining_visits"])

        started_at = active.started_at
        expires_at = active.expires_at
        remaining_visits = active.remaining_visits

        self.create_subscription(self.user, self.plan_2)

        active.refresh_from_db()

        self.assertEqual(active.status, GymSubscription.Status.ACTIVE)
        self.assertEqual(active.started_at, started_at)
        self.assertEqual(active.expires_at, expires_at)
        self.assertEqual(active.remaining_visits, remaining_visits)

    def test_second_pending_subscription_is_rejected(self):
        active = self.create_subscription(self.user, self.plan)
        active.remaining_visits = 2
        active.save(update_fields=["remaining_visits"])
        pending_1 = self.create_subscription(self.user, self.plan_2)
        with self.assertRaises(APIError) as raised:
            self.create_subscription(self.user, self.plan)

        self.assertEqual(raised.exception.error_code, GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS[0])
        self.assertEqual(active.status, GymSubscription.Status.ACTIVE)
        self.assertEqual(pending_1.status, GymSubscription.Status.PENDING)
        self.assertEqual(
            GymSubscription.objects.filter(
                subscriber=self.user,
                status=GymSubscription.Status.PENDING,
            ).count(),
            1,
        )

    def test_create_subscription_with_expired_active_subscription_activates(
        self,
    ):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        pending = self.create_subscription(self.user, self.plan_2)

        active.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            active.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            pending.status,
            GymSubscription.Status.ACTIVE,
        )


class GymSubscriptionActivationTests(GymSubscriptionTestBase):
    def test_activate_pending_subscription(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.PENDING,
        )

        subscription.activate()
        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertIsNotNone(subscription.started_at)
        self.assertIsNotNone(subscription.expires_at)
        # remaining_visits is set at creation from the plan, not at activation
        self.assertEqual(
            subscription.remaining_visits,
            self.plan.visit_limit,
        )
        self.assertIsNone(subscription.end_reason)
        self.assertIsNone(subscription.cancelled_at)

    def test_activate_preserves_remaining_visits(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.PENDING,
            remaining_visits=5,
        )

        subscription.activate()
        subscription.refresh_from_db()

        # activate() must not change remaining_visits
        self.assertEqual(subscription.remaining_visits, 5)

    def test_activate_uses_subscription_duration_months(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        before = timezone.now()

        subscription.activate()
        subscription.refresh_from_db()

        after = timezone.now()

        expected_min = before + relativedelta(months=subscription.duration_months)
        expected_max = after + relativedelta(months=subscription.duration_months)

        self.assertGreaterEqual(subscription.expires_at, expected_min)
        self.assertLessEqual(subscription.expires_at, expected_max)

    def test_activate_uses_plan_duration(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        before = timezone.now()

        subscription.activate()
        subscription.refresh_from_db()

        after = timezone.now()

        expected_min = before + relativedelta(months=self.plan_2.duration_months)
        expected_max = after + relativedelta(months=self.plan_2.duration_months)

        self.assertGreaterEqual(subscription.expires_at, expected_min)
        self.assertLessEqual(subscription.expires_at, expected_max)

    def test_activate_uses_plan_visit_limit(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        subscription.activate()
        subscription.refresh_from_db()

        # remaining_visits was set at creation from plan.visit_limit
        self.assertEqual(
            subscription.remaining_visits,
            self.plan_2.visit_limit,
        )

    def test_activate_non_pending_subscription_is_noop(self):
        started_at = timezone.now() - timedelta(days=1)
        expires_at = timezone.now() + timedelta(days=10)

        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            started_at=started_at,
            expires_at=expires_at,
        )

        subscription.activate()
        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(subscription.started_at, started_at)
        self.assertEqual(subscription.expires_at, expires_at)
        self.assertEqual(subscription.remaining_visits, 10)

    def test_activate_cancelled_subscription_is_noop(self):
        cancelled_at = timezone.now() - timedelta(days=1)

        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.CANCELLED,
            remaining_visits=10,
            cancelled_at=cancelled_at,
            end_reason=GymSubscription.EndReason.CANCELLED,
        )

        subscription.activate()
        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.CANCELLED,
        )
        self.assertEqual(subscription.cancelled_at, cancelled_at)

    def test_activate_expired_subscription_is_noop(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.EXPIRED,
            remaining_visits=0,
            expires_at=timezone.now() - timedelta(days=1),
            end_reason=GymSubscription.EndReason.TIME,
        )

        subscription.activate()
        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )


class GymSubscriptionExpirationTests(GymSubscriptionTestBase):
    def test_expire_active_subscription(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
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

    def test_expire_sets_visits_reason(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
            expires_at=timezone.now() + timedelta(days=10),
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

    def test_expire_non_active_subscription_is_noop(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.PENDING,
        )

        subscription.expire(GymSubscription.EndReason.TIME)
        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.PENDING,
        )
        self.assertIsNone(subscription.end_reason)

    def test_expire_cancelled_subscription_is_noop(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.CANCELLED,
            end_reason=GymSubscription.EndReason.CANCELLED,
            cancelled_at=timezone.now(),
        )

        subscription.expire(GymSubscription.EndReason.TIME)
        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.CANCELLED,
        )
        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.CANCELLED,
        )


class GymSubscriptionPromotionTests(GymSubscriptionTestBase):
    def test_promote_next_activates_only_same_gym_pending_subscription(self):
        first = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.PENDING,
        )

        second = self.create_raw_subscription(
            self.user,
            self.plan_3,
            status=GymSubscription.Status.PENDING,
        )

        result = GymSubscription.objects._promote_next_for_gym(self.user, self.gym)

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

    def test_promote_next_ignores_older_other_gym_pending(self):
        now = timezone.now()

        newer = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.PENDING,
            created_at=now + timedelta(seconds=10),
        )

        older = self.create_raw_subscription(
            self.user,
            self.plan_3,
            status=GymSubscription.Status.PENDING,
            created_at=now,
        )

        result = GymSubscription.objects._promote_next_for_gym(self.user, self.gym)

        older.refresh_from_db()
        newer.refresh_from_db()

        self.assertEqual(result.pk, newer.pk)
        self.assertEqual(
            older.status,
            GymSubscription.Status.PENDING,
        )
        self.assertEqual(
            newer.status,
            GymSubscription.Status.ACTIVE,
        )

    def test_promote_next_returns_none_when_active_subscription_exists(self):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        result = GymSubscription.objects._promote_next_for_gym(self.user, self.gym)

        active.refresh_from_db()
        pending.refresh_from_db()

        self.assertIsNone(result)
        self.assertEqual(
            active.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )

    def test_promote_next_returns_none_when_no_pending_subscription_exists(
        self,
    ):
        result = GymSubscription.objects._promote_next_for_gym(self.user, self.gym)

        self.assertIsNone(result)

    def test_promote_next_ignores_cancelled_subscriptions(self):
        cancelled = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.CANCELLED,
            end_reason=GymSubscription.EndReason.CANCELLED,
            cancelled_at=timezone.now(),
        )

        result = GymSubscription.objects._promote_next_for_gym(self.user, self.gym)

        cancelled.refresh_from_db()

        self.assertIsNone(result)
        self.assertEqual(
            cancelled.status,
            GymSubscription.Status.CANCELLED,
        )


class GymSubscriptionCancellationTests(GymSubscriptionTestBase):
    def test_cancelling_gym_a_preserves_active_gym_b(self):
        gym_a = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=10),
        )
        gym_b = self.create_raw_subscription(
            self.user,
            self.plan_3,
            status=GymSubscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=10),
        )

        GymSubscription.objects.cancel_subscription(gym_a)

        gym_a.refresh_from_db()
        gym_b.refresh_from_db()
        self.assertEqual(gym_a.status, GymSubscription.Status.CANCELLED)
        self.assertEqual(gym_b.status, GymSubscription.Status.ACTIVE)

    def test_model_cancel_only_changes_subscription_state(self):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
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
            active.end_reason,
            GymSubscription.EndReason.CANCELLED,
        )
        self.assertIsNotNone(active.cancelled_at)

        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )

    def test_cancel_subscription_cancels_active_and_promotes_next(self):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        result = GymSubscription.objects.cancel_subscription(active)

        active.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(result.pk, active.pk)
        self.assertEqual(
            active.status,
            GymSubscription.Status.CANCELLED,
        )
        self.assertEqual(
            pending.status,
            GymSubscription.Status.ACTIVE,
        )

    def test_cancel_subscription_does_not_promote_other_gym_pending(self):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        first_pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        second_pending = self.create_raw_subscription(
            self.user,
            self.plan_3,
            status=GymSubscription.Status.PENDING,
        )

        GymSubscription.objects.cancel_subscription(active)

        first_pending.refresh_from_db()
        second_pending.refresh_from_db()

        self.assertEqual(
            first_pending.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            second_pending.status,
            GymSubscription.Status.PENDING,
        )

    def test_cancel_subscription_with_no_pending_leaves_no_active_subscription(
        self,
    ):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        GymSubscription.objects.cancel_subscription(active)

        active.refresh_from_db()

        self.assertEqual(
            active.status,
            GymSubscription.Status.CANCELLED,
        )

        self.assertFalse(
            GymSubscription.objects.filter(
                subscriber=self.user,
                status=GymSubscription.Status.ACTIVE,
            ).exists()
        )

    def test_cancel_pending_subscription_does_not_affect_active_subscription(
        self,
    ):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        GymSubscription.objects.cancel_subscription(pending)

        active.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            active.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            pending.status,
            GymSubscription.Status.CANCELLED,
        )

    def test_cancel_pending_subscription_does_not_promote_other_gym(
        self,
    ):
        first = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.PENDING,
        )

        second = self.create_raw_subscription(
            self.user,
            self.plan_3,
            status=GymSubscription.Status.PENDING,
        )

        GymSubscription.objects.cancel_subscription(first)

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertEqual(
            first.status,
            GymSubscription.Status.CANCELLED,
        )
        self.assertEqual(
            second.status,
            GymSubscription.Status.PENDING,
        )

    def test_cancel_expired_subscription_does_not_promote_pending_subscription(
        self,
    ):
        expired = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.EXPIRED,
            remaining_visits=0,
            expires_at=timezone.now() - timedelta(days=1),
            end_reason=GymSubscription.EndReason.TIME,
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        GymSubscription.objects.cancel_subscription(expired)

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

    def test_cancel_already_cancelled_subscription_does_not_promote_pending(
        self,
    ):
        cancelled = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.CANCELLED,
            remaining_visits=10,
            end_reason=GymSubscription.EndReason.CANCELLED,
            cancelled_at=timezone.now(),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        GymSubscription.objects.cancel_subscription(cancelled)

        cancelled.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            cancelled.status,
            GymSubscription.Status.CANCELLED,
        )
        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )

    def test_cancelled_subscription_keeps_cancelled_at(self):
        cancelled_at = timezone.now() - timedelta(hours=1)

        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.CANCELLED,
            end_reason=GymSubscription.EndReason.CANCELLED,
            cancelled_at=cancelled_at,
        )

        GymSubscription.objects.cancel_subscription(subscription)

        subscription.refresh_from_db()

        self.assertEqual(subscription.cancelled_at, cancelled_at)


class GymSubscriptionCheckInTests(GymSubscriptionTestBase):
    def test_active_subscription_is_used_before_same_gym_pending(self):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=2,
            expires_at=timezone.now() + timedelta(days=10),
        )
        pending = self.create_raw_subscription(self.user, self.plan_2)

        used = GymSubscription.objects.consume_visit(self.user, self.gym)

        active.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(used.pk, active.pk)
        self.assertEqual(active.remaining_visits, 1)
        self.assertEqual(active.status, GymSubscription.Status.ACTIVE)
        self.assertEqual(pending.status, GymSubscription.Status.PENDING)
        self.assertEqual(pending.remaining_visits, self.plan_2.visit_limit)

    def test_last_visit_promotes_only_same_gym_pending(self):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status="ACTIVE",
            remaining_visits=1,
            expires_at=timezone.now() + timedelta(days=10),
        )
        other_user_pending = self.create_raw_subscription(self.user_2, self.plan_3)
        other_gym_pending = self.create_raw_subscription(self.user, self.plan_3)
        next_subscription = self.create_raw_subscription(self.user, self.plan_2)

        result = GymSubscription.objects.consume_visit(self.user, self.gym)

        for subscription in (active, next_subscription, other_gym_pending, other_user_pending):
            subscription.refresh_from_db()
        self.assertEqual(result.pk, active.pk)
        self.assertEqual(active.status, "EXPIRED")
        self.assertEqual(active.end_reason, "VISITS")
        self.assertEqual(active.remaining_visits, 0)
        self.assertEqual(next_subscription.status, "ACTIVE")
        self.assertEqual(next_subscription.remaining_visits, 60)
        self.assertIsNotNone(next_subscription.started_at)
        self.assertEqual(
            next_subscription.expires_at,
            next_subscription.started_at + relativedelta(months=3),
        )
        self.assertEqual(other_gym_pending.status, "PENDING")
        self.assertEqual(other_user_pending.status, "PENDING")
        self.assertEqual(
            GymSubscription.objects.filter(subscriber=self.user, status="ACTIVE").count(),
            1,
        )

    def test_no_active_subscription_promotes_oldest_pending_for_requested_gym(self):
        expired = self.create_raw_subscription(
            self.user,
            self.plan,
            status="EXPIRED",
            remaining_visits=0,
            end_reason="VISITS",
        )
        older_other_gym = self.create_raw_subscription(self.user, self.plan_2)
        next_subscription = self.create_raw_subscription(self.user, self.plan_3)

        result = GymSubscription.objects.consume_visit(self.user, self.gym_2)

        for subscription in (expired, older_other_gym, next_subscription):
            subscription.refresh_from_db()
        self.assertEqual(result.pk, next_subscription.pk)
        self.assertEqual(next_subscription.status, "ACTIVE")
        self.assertEqual(next_subscription.remaining_visits, 19)
        self.assertEqual(expired.status, "EXPIRED")
        self.assertEqual(expired.remaining_visits, 0)
        self.assertEqual(older_other_gym.status, "PENDING")
        self.assertEqual(
            GymSubscription.objects.filter(subscriber=self.user, status="ACTIVE").count(),
            1,
        )

    def test_no_active_subscription_does_not_use_another_gyms_queue(self):
        pending = self.create_raw_subscription(self.user, self.plan_3)
        with self.assertRaises(APIError) as raised:
            GymSubscription.objects.consume_visit(self.user, self.gym)
        self.assertEqual(raised.exception.error_code, "SUBS_003")
        pending.refresh_from_db()
        self.assertEqual(pending.status, "PENDING")
        self.assertEqual(pending.remaining_visits, 20)
        self.assertIsNone(pending.started_at)

    def test_no_active_subscription_does_not_use_another_users_queue(self):
        pending = self.create_raw_subscription(self.user_2, self.plan_3)
        with self.assertRaises(APIError) as raised:
            GymSubscription.objects.consume_visit(self.user, self.gym_2)
        self.assertEqual(raised.exception.error_code, "SUBS_003")
        pending.refresh_from_db()
        self.assertEqual(pending.status, "PENDING")
        self.assertEqual(pending.remaining_visits, 20)

    def test_valid_active_subscription_does_not_prevent_other_gym_promotion(self):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status="ACTIVE",
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )
        pending = self.create_raw_subscription(self.user, self.plan_3)
        result = GymSubscription.objects.consume_visit(self.user, self.gym_2)
        active.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(active.status, "ACTIVE")
        self.assertEqual(active.remaining_visits, 10)
        self.assertEqual(result.pk, pending.pk)
        self.assertEqual(pending.status, "ACTIVE")
        self.assertEqual(pending.remaining_visits, 19)

    def test_check_in_decrements_remaining_visits(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        result = GymSubscription.objects.consume_visit(
            self.user,
            self.gym,
        )

        subscription.refresh_from_db()

        self.assertEqual(result.pk, subscription.pk)
        self.assertEqual(subscription.remaining_visits, 9)
        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )

    def test_check_in_on_wrong_gym_does_not_consume_visit(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.consume_visit(
                self.user,
                self.gym_2,
            )

        subscription.refresh_from_db()

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )
        self.assertEqual(subscription.remaining_visits, 10)
        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )

    def test_check_in_without_active_subscription_raises_error(self):
        with self.assertRaises(APIError) as context:
            GymSubscription.objects.consume_visit(
                self.user,
                self.gym,
            )

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

    def test_check_in_expires_time_expired_subscription(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.consume_visit(
                self.user,
                self.gym,
            )

        subscription.refresh_from_db()

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )
        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.TIME,
        )

    def test_check_in_expires_visits_exhausted_subscription(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=0,
            expires_at=timezone.now() + timedelta(days=10),
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.consume_visit(
                self.user,
                self.gym,
            )

        subscription.refresh_from_db()

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )
        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.VISITS,
        )

    def test_check_in_expired_subscription_promotes_next_subscription(self):
        expired = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        result = GymSubscription.objects.consume_visit(
            self.user,
            self.gym,
        )

        expired.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(result.pk, pending.pk)
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
            self.plan_2.visit_limit - 1,
        )

    def test_check_in_expired_subscription_does_not_promote_other_gym(self):
        expired = self.create_raw_subscription(
            self.user,
            self.plan,  # Gym A
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_3,  # Gym B
            status=GymSubscription.Status.PENDING,
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.consume_visit(self.user, self.gym)  # Gym A

        expired.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )
        self.assertEqual(expired.status, GymSubscription.Status.EXPIRED)
        self.assertEqual(pending.status, GymSubscription.Status.PENDING)

    def test_check_in_last_visit_expires_subscription(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=1,
            expires_at=timezone.now() + timedelta(days=10),
        )

        result = GymSubscription.objects.consume_visit(
            self.user,
            self.gym,
        )

        subscription.refresh_from_db()

        self.assertEqual(result.pk, subscription.pk)
        self.assertEqual(subscription.remaining_visits, 0)
        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            subscription.end_reason,
            GymSubscription.EndReason.VISITS,
        )

    def test_check_in_last_visit_promotes_next_subscription(self):
        first = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=1,
            expires_at=timezone.now() + timedelta(days=10),
        )

        second = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        result = GymSubscription.objects.consume_visit(
            self.user,
            self.gym,
        )

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertEqual(result.pk, first.pk)
        self.assertEqual(
            first.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            first.end_reason,
            GymSubscription.EndReason.VISITS,
        )
        self.assertEqual(
            second.status,
            GymSubscription.Status.ACTIVE,
        )

    def test_check_in_last_visit_with_no_pending_subscription_leaves_no_active(
        self,
    ):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=1,
            expires_at=timezone.now() + timedelta(days=10),
        )

        GymSubscription.objects.consume_visit(
            self.user,
            self.gym,
        )

        subscription.refresh_from_db()

        self.assertEqual(
            subscription.status,
            GymSubscription.Status.EXPIRED,
        )

        self.assertFalse(
            GymSubscription.objects.filter(
                subscriber=self.user,
                status=GymSubscription.Status.ACTIVE,
            ).exists()
        )

    def test_check_in_does_not_decrement_other_gym_subscription(self):
        first = self.create_raw_subscription(
            self.user,
            self.plan,  # Gym A, expired
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        second = self.create_raw_subscription(
            self.user,
            self.plan_3,  # Gym B, pending
            status=GymSubscription.Status.PENDING,
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.consume_visit(self.user, self.gym)  # Gym A

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )
        self.assertEqual(first.status, GymSubscription.Status.EXPIRED)
        self.assertEqual(second.status, GymSubscription.Status.PENDING)
        # Pending subscription retains its plan visit_limit until activated
        self.assertEqual(second.remaining_visits, self.plan_3.visit_limit)

    def test_check_in_does_not_decrement_when_subscription_has_one_visit_and_wrong_gym(
        self,
    ):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=1,
            expires_at=timezone.now() + timedelta(days=10),
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.consume_visit(
                self.user,
                self.gym_2,
            )

        subscription.refresh_from_db()

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )
        self.assertEqual(subscription.remaining_visits, 1)
        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )


class GymSubscriptionConstraintTests(GymSubscriptionTestBase):

    def test_only_one_active_subscription_per_user(self):
        first = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_raw_subscription(
                    self.user,
                    self.plan_2,
                    status=GymSubscription.Status.ACTIVE,
                    remaining_visits=10,
                    expires_at=timezone.now() + timedelta(days=10),
                )

        first.refresh_from_db()

        self.assertEqual(
            first.status,
            GymSubscription.Status.ACTIVE,
        )

    def test_only_one_pending_subscription_per_user_and_gym(self):
        first = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.PENDING,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_raw_subscription(
                    self.user,
                    self.plan_2,
                    status=GymSubscription.Status.PENDING,
                )

        self.assertEqual(
            first.status,
            GymSubscription.Status.PENDING,
        )

    def test_active_subscriptions_at_different_gyms_are_allowed(self):
        first = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=10),
        )
        second = self.create_raw_subscription(
            self.user,
            self.plan_3,
            status=GymSubscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.assertNotEqual(first.gym_id, second.gym_id)

    def test_active_subscriptions_for_different_users_are_allowed(self):
        first = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        second = self.create_raw_subscription(
            self.user_2,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.assertNotEqual(first.subscriber_id, second.subscriber_id)

    def test_pending_and_active_subscription_can_exist_for_same_user(self):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        self.assertEqual(
            active.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )

    def test_multiple_expired_subscriptions_are_allowed(self):
        first = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.EXPIRED,
            remaining_visits=0,
            expires_at=timezone.now() - timedelta(days=2),
            end_reason=GymSubscription.EndReason.TIME,
        )

        second = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.EXPIRED,
            remaining_visits=0,
            expires_at=timezone.now() - timedelta(days=1),
            end_reason=GymSubscription.EndReason.VISITS,
        )

        self.assertEqual(
            first.status,
            GymSubscription.Status.EXPIRED,
        )
        self.assertEqual(
            second.status,
            GymSubscription.Status.EXPIRED,
        )


class GymSubscriptionTransactionTests(GymSubscriptionTestBase):
    def test_create_subscription_rolls_back_when_activation_fails(self):
        initial_count = GymSubscription.objects.count()

        with patch.object(
            GymSubscription,
            "activate",
            side_effect=APIError(GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS),
        ):
            with self.assertRaises(APIError):
                self.create_subscription(self.user, self.plan)

        self.assertEqual(
            GymSubscription.objects.count(),
            initial_count,
        )

        self.assertFalse(
            GymSubscription.objects.filter(
                subscriber=self.user,
            ).exists()
        )

    def test_cancel_subscription_rolls_back_when_promotion_fails(self):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        with patch.object(
            GymSubscription,
            "activate",
            side_effect=APIError(GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS),
        ):
            with self.assertRaises(APIError):
                GymSubscription.objects.cancel_subscription(active)

        active.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            active.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )

    def test_check_in_wrong_gym_expires_old_but_does_not_promote_other_gym(self):
        expired = self.create_raw_subscription(
            self.user,
            self.plan,  # Gym A
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_3,  # Gym B
            status=GymSubscription.Status.PENDING,
        )

        with self.assertRaises(APIError):
            GymSubscription.objects.consume_visit(self.user, self.gym)  # Gym A

        expired.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(expired.status, GymSubscription.Status.EXPIRED)
        self.assertEqual(pending.status, GymSubscription.Status.PENDING)

    def test_check_in_wrong_gym_does_not_roll_back_visit_decrement_before_error(
        self,
    ):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects.consume_visit(
                self.user,
                self.gym_2,
            )

        subscription.refresh_from_db()

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )
        self.assertEqual(subscription.remaining_visits, 10)


class GymSubscriptionManagerInternalTests(GymSubscriptionTestBase):
    def test_activate_subscription_private_helper_activates_pending_subscription(
        self,
    ):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.PENDING,
        )

        result = GymSubscription.objects._activate_subscription(subscription)

        subscription.refresh_from_db()

        self.assertEqual(result.pk, subscription.pk)
        self.assertEqual(
            subscription.status,
            GymSubscription.Status.ACTIVE,
        )

    def test_activate_subscription_private_helper_rejects_existing_active_subscription(
        self,
    ):
        active = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        pending = self.create_raw_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        with self.assertRaises(APIError) as context:
            GymSubscription.objects._activate_subscription(pending)

        active.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(
            context.exception.error_code,
            GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS[0],
        )
        self.assertEqual(
            active.status,
            GymSubscription.Status.ACTIVE,
        )
        self.assertEqual(
            pending.status,
            GymSubscription.Status.PENDING,
        )

    def test_has_active_subscription_returns_true(self):
        self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.assertTrue(GymSubscription.objects._has_active_subscription(self.user, self.gym))

    def test_has_active_subscription_returns_false(self):
        self.assertFalse(GymSubscription.objects._has_active_subscription(self.user, self.gym))

    def test_has_active_subscription_can_exclude_subscription(self):
        subscription = self.create_raw_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.assertFalse(
            GymSubscription.objects._has_active_subscription(
                self.user,
                self.gym,
                exclude_pk=subscription.pk,
            )
        )

        self.assertTrue(GymSubscription.objects._has_active_subscription(self.user, self.gym))


class GymSubscriptionRecoveryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(phone_number="09120000001")
        self.gym = Gym.objects.create(name="Test Gym")
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Monthly",
            description="Monthly membership",
            duration_months=1,
            visit_limit=30,
            price=1000,
        )
        order = Order.objects.create(
            buyer=self.user,
            status=Order.Status.SUCCEEDED,
            subtotal_amount=1000,
            discount_amount=0,
            tax_amount=0,
            total_amount=1000,
            succeeded_at=timezone.now(),
            commerce_product=plan.id,
            product_snapshot={},
        )
        self.pending = GymSubscription.objects.create(
            subscriber=self.user,
            plan=plan,
            order=order,
            status="PENDING",
            initial_visits=plan.visit_limit,
            duration_months=1,
            remaining_visits=30,
        )

    def test_concurrent_consumption_promotes_once_and_preserves_both_decrements(self):
        barrier = Barrier(2)

        def consume_visit():
            try:
                barrier.wait(timeout=10)
                with transaction.atomic():
                    subscription = GymSubscription.objects.consume_visit(self.user, self.gym)
                    return subscription.pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(consume_visit) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]

        self.assertEqual(results, [self.pending.pk, self.pending.pk])
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, "ACTIVE")
        self.assertEqual(self.pending.remaining_visits, 28)
        self.assertEqual(
            GymSubscription.objects.filter(subscriber=self.user, status="ACTIVE").count(),
            1,
        )
