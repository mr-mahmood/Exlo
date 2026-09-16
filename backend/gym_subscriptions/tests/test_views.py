# gym_subscriptions/tests/test_views.py
# type: ignore

import uuid
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from commerce_orders.models import CommerceProduct, Order, OrderItem
from core.errors import GymSubscriptionError
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User


class SubscriptionViewTestBase(TestCase):
    def setUp(self):
        settings.DEBUG = True
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
            duration_month=1,
            visit_limit=30,
            price=Decimal("10000"),
        )
        self.plan_2 = GymMembershipPlan.objects.create_plan(
            name="Three Month Plan",
            gym=self.gym,
            duration_month=3,
            visit_limit=60,
            price=Decimal("20000"),
        )

        self.list_url = reverse("gym_subscriptions:gym-subscription-list")

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def make_order_item(self, user, plan):
        order = Order.objects.create(
            buyer=user,
            status=Order.Status.PAID,
            subtotal_amount=Decimal("100000"),
            discount_amount=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("100000"),
            paid_at=timezone.now(),
        )
        return OrderItem.objects.create(
            commerce_product=plan.id,
            order=order,
            item_type=CommerceProduct.ProductType.GYM_MEMBERSHIP,
            item_snapshot={"id": str(plan.pk), "name": plan.name},
            quantity=1,
            unit_price=Decimal("100000"),
            subtotal_amount=Decimal("100000"),
            discount_amount=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("100000"),
        )

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
        order_item = self.make_order_item(user, plan)
        return GymSubscription.objects.create(
            subscriber=user,
            plan=plan,
            order_item=order_item,
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
        response = self.client.get(self.detail_url(uuid.uuid4()))

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
        self.assertEqual(payload["plan"]["price"], "10000.00")

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
        response = self.client.post(self.cancel_url(uuid.uuid4()))

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
