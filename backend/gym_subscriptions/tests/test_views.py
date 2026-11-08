# gym_subscriptions/tests/test_views.py


import uuid
from datetime import timedelta
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from commerce_orders.models import Order
from core.cache import USER_SUBSCRIPTION, cache_key
from core.errors import GymSubscriptionError
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User


class SubscriptionViewTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            phone_number="09120000001",
            password="testpassword123",
        )
        self.other_user = User.objects.create_user(
            phone_number="09120000002",
            password="testpassword123",
        )

        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Tehran",
            city="Tehran",
            address="Test Address",
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

        self.list_url = reverse("gym_subscriptions:gym-subscription-list")

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def make_order(self, user, plan):
        order = Order.objects.create(
            buyer=user,
            status=Order.Status.PAID,
            subtotal_amount=100000,
            discount_amount=0,
            tax_amount=0,
            total_amount=100000,
            paid_at=timezone.now(),
            commerce_product=plan.id,
            product_snapshot={"id": str(plan.pk), "name": plan.name},
        )
        return order

    def make_subscription(
        self,
        user,
        plan,
        *,
        status=GymSubscription.Status.PENDING,
        remaining_visits=0,
        started_at=None,
        expires_at=None,
        end_reason=None,
        cancelled_at=None
    ):
        order = self.make_order(user, plan)
        return GymSubscription.objects.create(
            subscriber=user,
            plan=plan,
            order=order,
            status=status,
            remaining_visits=remaining_visits,
            started_at=started_at,
            expires_at=expires_at,
            end_reason=end_reason,
            cancelled_at=cancelled_at,
        )

    def detail_url(self, subscription_id):
        return reverse(
            "gym_subscriptions:gym-subscription-detail",
            kwargs={"subscription_id": subscription_id},
        )

    def cancel_url(self, subscription_id):
        return reverse(
            "gym_subscriptions:gym-subscription-cancel",
            kwargs={"subscription_id": subscription_id},
        )


# ============================================================================
# Authentication & permission
# ============================================================================
class SubscriptionAuthTests(SubscriptionViewTestBase):
    def test_list_requires_authentication(self):
        response = self.client.get(self.list_url)
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_detail_requires_authentication(self):
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
        )
        response = self.client.get(self.detail_url(sub.id))
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_cancel_requires_authentication(self):
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
        )
        response = self.client.post(self.cancel_url(sub.id))
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_inactive_user_cannot_list(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.authenticate(self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_inactive_user_cannot_cancel(self):
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
        )
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.authenticate(self.user)
        response = self.client.post(self.cancel_url(sub.id))
        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )


# ============================================================================
# List view
# ============================================================================
class SubscriptionListTests(SubscriptionViewTestBase):
    def test_returns_only_own_subscriptions(self):
        self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.make_subscription(
            self.other_user,
            self.plan_2,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["subscriptions"]), 1)
        self.assertEqual(
            response.data["subscriptions"][0]["plan"]["id"],
            self.plan.pk,
        )

    def test_returns_empty_when_no_subscriptions(self):
        self.authenticate(self.user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["subscriptions"], [])

    def test_filters_by_status_uppercase(self):
        self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.make_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        self.authenticate(self.user)
        response = self.client.get(self.list_url, {"status": "ACTIVE"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["subscriptions"]), 1)
        self.assertEqual(
            response.data["subscriptions"][0]["status"],
            "ACTIVE",
        )

    def test_filters_by_status_lowercase(self):
        self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.make_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        self.authenticate(self.user)
        response = self.client.get(self.list_url, {"status": "active"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["subscriptions"]), 1)

    def test_invalid_status_is_ignored_returns_all(self):
        self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.make_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        self.authenticate(self.user)
        response = self.client.get(self.list_url, {"status": "garbage"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["subscriptions"]), 2)

    def test_filter_by_pending_status(self):
        self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )
        self.make_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        self.authenticate(self.user)
        response = self.client.get(self.list_url, {"status": "PENDING"})

        self.assertEqual(len(response.data["subscriptions"]), 1)
        self.assertEqual(
            response.data["subscriptions"][0]["status"],
            "PENDING",
        )

    def test_ordering_newest_first(self):
        now = timezone.now()
        older = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.EXPIRED,
            end_reason=GymSubscription.EndReason.TIME,
        )
        newer = self.make_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )
        GymSubscription.objects.filter(pk=older.pk).update(
            created_at=now - timedelta(days=1)
        )
        GymSubscription.objects.filter(pk=newer.pk).update(created_at=now)

        self.authenticate(self.user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.data["subscriptions"][0]["id"], str(newer.pk))
        self.assertEqual(response.data["subscriptions"][1]["id"], str(older.pk))

    def test_serializes_nested_plan_and_gym(self):
        self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)
        response = self.client.get(self.list_url)

        sub = response.data["subscriptions"][0]
        self.assertIn("plan", sub)
        self.assertIn("gym", sub["plan"])
        self.assertEqual(sub["plan"]["gym"]["id"], str(self.gym.pk))
        self.assertEqual(sub["plan"]["name"], "Monthly Plan")

    def test_serializes_top_level_gym(self):
        self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)
        response = self.client.get(self.list_url)

        sub = response.data["subscriptions"][0]
        self.assertIn("gym", sub)
        self.assertIsInstance(sub["gym"], dict)
        self.assertEqual(sub["gym"]["id"], str(self.gym.pk))
        self.assertEqual(sub["gym"]["name"], "Test Gym")
        # top-level gym should match nested plan gym
        self.assertEqual(sub["gym"], sub["plan"]["gym"])

    def test_pagination_shape(self):
        self.authenticate(self.user)
        response = self.client.get(self.list_url)

        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("subscriptions", response.data)


# ============================================================================
# Detail view
# ============================================================================
class SubscriptionDetailTests(SubscriptionViewTestBase):
    def test_returns_own_subscription(self):
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)
        response = self.client.get(self.detail_url(sub.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["subscription"]["id"], str(sub.id))

    def test_other_users_subscription_returns_subscription_not_found(self):
        sub = self.make_subscription(
            self.other_user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)
        response = self.client.get(self.detail_url(sub.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.SUBSCRIPTION_NOT_FOUND[0],
        )

    def test_nonexistent_subscription_returns_subscription_not_found(self):
        self.authenticate(self.user)
        response = self.client.get(self.detail_url(uuid.uuid7()))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.SUBSCRIPTION_NOT_FOUND[0],
        )

    def test_malformed_uuid_returns_subscription_not_found(self):
        self.authenticate(self.user)
        response = self.client.get("/api/subscriptions/not-a-uuid/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_serializes_nested_plan_and_gym(self):
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)
        response = self.client.get(self.detail_url(sub.id))

        payload = response.data["subscription"]
        self.assertEqual(payload["plan"]["gym"]["id"], str(self.gym.pk))
        self.assertEqual(payload["plan"]["name"], "Monthly Plan")
        self.assertEqual(payload["plan"]["price"], 10000)

    def test_serializes_top_level_gym(self):
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)
        response = self.client.get(self.detail_url(sub.id))

        payload = response.data["subscription"]
        self.assertIn("gym", payload)
        self.assertIsInstance(payload["gym"], dict)
        self.assertEqual(payload["gym"]["id"], str(self.gym.pk))
        self.assertEqual(payload["gym"]["name"], "Test Gym")
        self.assertEqual(payload["gym"], payload["plan"]["gym"])

    def test_serializes_remaining_visits_and_expires_at(self):
        expires = timezone.now() + timedelta(days=15)
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=42,
            started_at=timezone.now(),
            expires_at=expires,
        )

        self.authenticate(self.user)
        response = self.client.get(self.detail_url(sub.id))

        payload = response.data["subscription"]
        self.assertEqual(payload["remaining_visits"], 42)
        self.assertEqual(payload["status"], "ACTIVE")
        self.assertIsNotNone(payload["expires_at"])


# ============================================================================
# Cancel view
# ============================================================================
class SubscriptionCancelTests(SubscriptionViewTestBase):
    def test_cancel_active_subscription(self):
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)
        response = self.client.post(self.cancel_url(sub.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sub.refresh_from_db()
        self.assertEqual(sub.status, GymSubscription.Status.CANCELLED)
        self.assertEqual(sub.end_reason, GymSubscription.EndReason.CANCELLED)
        self.assertIsNotNone(sub.cancelled_at)

    def test_cancel_pending_subscription(self):
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.PENDING,
        )

        self.authenticate(self.user)
        response = self.client.post(self.cancel_url(sub.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sub.refresh_from_db()
        self.assertEqual(sub.status, GymSubscription.Status.CANCELLED)

    def test_cancel_is_idempotent(self):
        cancelled_at = timezone.now() - timedelta(hours=1)
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.CANCELLED,
            end_reason=GymSubscription.EndReason.CANCELLED,
            cancelled_at=cancelled_at,
        )

        self.authenticate(self.user)
        response = self.client.post(self.cancel_url(sub.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sub.refresh_from_db()
        self.assertEqual(sub.status, GymSubscription.Status.CANCELLED)
        self.assertEqual(sub.cancelled_at, cancelled_at)

    def test_cancel_expired_subscription_is_noop(self):
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.EXPIRED,
            end_reason=GymSubscription.EndReason.TIME,
        )

        self.authenticate(self.user)
        response = self.client.post(self.cancel_url(sub.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sub.refresh_from_db()
        self.assertEqual(sub.status, GymSubscription.Status.EXPIRED)
        self.assertEqual(sub.end_reason, GymSubscription.EndReason.TIME)

    def test_cannot_cancel_other_users_subscription(self):
        sub = self.make_subscription(
            self.other_user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)
        response = self.client.post(self.cancel_url(sub.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        sub.refresh_from_db()
        self.assertEqual(sub.status, GymSubscription.Status.ACTIVE)

    def test_cancel_nonexistent_returns_404(self):
        self.authenticate(self.user)
        response = self.client.post(self.cancel_url(uuid.uuid7()))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cancelling_active_promotes_oldest_pending(self):
        active = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )
        first_pending = self.make_subscription(
            self.user,
            self.plan_2,
            status=GymSubscription.Status.PENDING,
        )

        self.authenticate(self.user)
        response = self.client.post(self.cancel_url(active.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        active.refresh_from_db()
        first_pending.refresh_from_db()
        self.assertEqual(active.status, GymSubscription.Status.CANCELLED)
        self.assertEqual(first_pending.status, GymSubscription.Status.ACTIVE)

    def test_cancel_does_not_change_other_users_subscription(self):
        mine = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )
        theirs = self.make_subscription(
            self.other_user,
            self.plan_2,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)
        self.client.post(self.cancel_url(mine.id))

        theirs.refresh_from_db()
        self.assertEqual(theirs.status, GymSubscription.Status.ACTIVE)


class SubscriptionCacheInvalidationTests(SubscriptionViewTestBase):
    def assert_subscription_states(self, expected):
        list_response = self.client.get(self.list_url)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        states = {
            item["id"]: item["status"]
            for item in list_response.data["subscriptions"]
        }
        self.assertEqual(states, {str(sub.pk): state for sub, state in expected})
        for state in ("ACTIVE", "PENDING", "EXPIRED", "CANCELLED"):
            filtered = self.client.get(self.list_url, {"status": state})
            self.assertEqual(filtered.status_code, status.HTTP_200_OK)
            self.assertEqual(
                {item["id"] for item in filtered.data["subscriptions"]},
                {str(sub.pk) for sub, current in expected if current == state},
            )
        for sub, state in expected:
            detail = self.client.get(self.detail_url(sub.pk))
            self.assertEqual(detail.status_code, status.HTTP_200_OK)
            self.assertEqual(detail.data["subscription"]["status"], state)

    def test_activation_refreshes_cached_list_and_detail(self):
        pending = self.make_subscription(self.user, self.plan, remaining_visits=30)
        self.authenticate(self.user)
        self.assert_subscription_states([(pending, "PENDING")])

        with self.captureOnCommitCallbacks(execute=True):
            pending.activate()

        pending.refresh_from_db()
        self.assertEqual(pending.status, "ACTIVE")
        self.assert_subscription_states([(pending, "ACTIVE")])

    def test_cancellation_refreshes_cancelled_and_promoted_details(self):
        active = self.make_subscription(
            self.user, self.plan, status=GymSubscription.Status.ACTIVE,
            remaining_visits=10, expires_at=timezone.now() + timedelta(days=10),
        )
        pending = self.make_subscription(
            self.user, self.plan_2, remaining_visits=30,
        )
        self.authenticate(self.user)
        self.assert_subscription_states([(active, "ACTIVE"), (pending, "PENDING")])

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.cancel_url(active.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        active.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(active.status, "CANCELLED")
        self.assertEqual(pending.status, "ACTIVE")
        self.assert_subscription_states([(active, "CANCELLED"), (pending, "ACTIVE")])

    def test_expiry_refreshes_cached_list_and_detail(self):
        active = self.make_subscription(
            self.user, self.plan, status=GymSubscription.Status.ACTIVE,
            remaining_visits=0, expires_at=timezone.now() + timedelta(days=10),
        )
        self.authenticate(self.user)
        self.assert_subscription_states([(active, "ACTIVE")])

        with self.captureOnCommitCallbacks(execute=True):
            active.expire(reason=GymSubscription.EndReason.VISITS)

        active.refresh_from_db()
        self.assertEqual(active.status, "EXPIRED")
        self.assert_subscription_states([(active, "EXPIRED")])

    def test_rolled_back_transition_keeps_cached_state(self):
        pending = self.make_subscription(self.user, self.plan, remaining_visits=30)
        self.authenticate(self.user)
        self.assert_subscription_states([(pending, "PENDING")])
        original_key = cache_key(USER_SUBSCRIPTION, self.user.pk, pending.pk)

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                pending.activate()
                self.assertEqual(
                    cache_key(USER_SUBSCRIPTION, self.user.pk, pending.pk),
                    original_key,
                )
                raise RuntimeError("roll back activation")

        pending.refresh_from_db()
        self.assertEqual(pending.status, "PENDING")
        self.assertEqual(
            cache_key(USER_SUBSCRIPTION, self.user.pk, pending.pk), original_key
        )
        self.assert_subscription_states([(pending, "PENDING")])


# ============================================================================
# Query count / N+1 regression
# ============================================================================
class SubscriptionQueryCountTests(SubscriptionViewTestBase):
    def test_list_does_not_n_plus_one(self):
        for _ in range(5):
            self.make_subscription(
                self.user,
                self.plan,
                status=GymSubscription.Status.EXPIRED,
                end_reason=GymSubscription.EndReason.TIME,
            )

        self.authenticate(self.user)

        # 1 count query + 1 fetch (with select_related plan + plan__gym)
        with self.assertNumQueries(2):
            self.client.get(self.list_url)

    def test_detail_does_not_n_plus_one(self):
        sub = self.make_subscription(
            self.user,
            self.plan,
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
            expires_at=timezone.now() + timedelta(days=10),
        )

        self.authenticate(self.user)

        # 1 fetch (with select_related plan + plan__gym)
        with self.assertNumQueries(1):
            self.client.get(self.detail_url(sub.id))
