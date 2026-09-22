# users_nfc_cards/tests/test_views.py
# type: ignore

from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from commerce_orders.models import CommerceProduct, Order, OrderItem
from gym.models import Gym
from gym_auth.models import UserGymRole
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User
from users_nfc_cards.models import UserNfcCard
from rest_framework import status
from django.conf import settings


class ViewTestBase(TestCase):
    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()

        self.gym_a = Gym.objects.create(name="Gym A")

        self.admin = User.objects.create_superuser(
            phone_number="09120000020",
            password="x",
            first_name="A",
            last_name="D",
            role=User.Role.ADMIN,
        )
        self.owner_a = User.objects.create_user(
            phone_number="09120000021",
            password="x",
            first_name="O",
            last_name="A",
        )
        self.regular = User.objects.create_user(
            phone_number="09120000022",
            password="x",
            first_name="R",
            last_name="R",
        )
        self.target = User.objects.create_user(
            phone_number="09120000023",
            password="x",
            first_name="T",
            last_name="T",
        )

        UserGymRole.objects.create(
            user=self.owner_a, gym=self.gym_a, role=UserGymRole.Role.OWNER
        )

        self.plan_a = GymMembershipPlan.objects.create_plan(
            name="Plan A",
            gym=self.gym_a,
            duration_months=1,
            visit_limit=30,
            price=1000,
        )

    def _make_order_item(self, user, plan):
        order = Order.objects.create(
            buyer=user,
            status=Order.Status.PAID,
            subtotal_amount=0,
            discount_amount=0,
            tax_amount=0,
            total_amount=0,
            paid_at=timezone.now(),
        )
        return OrderItem.objects.create(
            commerce_product=plan.id,
            order=order,
            item_type=CommerceProduct.ProductType.GYM_MEMBERSHIP,
            item_snapshot={},
            quantity=1,
            unit_price=0,
            subtotal_amount=0,
            discount_amount=0,
            tax_amount=0,
            total_amount=0,
        )

    def create_active_subscription(self, user, plan):
        return GymSubscription.objects.create_subscription(
            subscriber=user,
            order_item=self._make_order_item(user, plan),
        )

    def url(self, user_id):
        return reverse("users_nfc_cards:assign", args=[user_id])

    def assign(self, as_user, target_id, uid="04A32B", method="post"):
        self.client.force_authenticate(user=as_user)
        return getattr(self.client, method)(
            self.url(target_id), {"uid": uid}, format="json"
        )


class AssignCardViewTests(ViewTestBase):
    def test_admin_can_assign(self):
        response = self.assign(self.admin, self.target.id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            UserNfcCard.objects.filter(user=self.target, uid="04A32B").exists()
        )

    def test_owner_can_assign_to_member_of_their_gym(self):
        self.create_active_subscription(self.target, self.plan_a)

        response = self.assign(self.owner_a, self.target.id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_owner_cannot_assign_to_non_member(self):
        response = self.assign(self.owner_a, self.target.id)

        # Your handler turns 403 into 404 — adjust if different.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(UserNfcCard.objects.filter(user=self.target).exists())

    def test_regular_user_cannot_assign(self):
        self.create_active_subscription(self.target, self.plan_a)

        response = self.assign(self.regular, self.target.id)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_cannot_assign(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.url(self.target.id), {"uid": "04A32B"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_target_user_does_not_exist(self):
        from uuid import uuid4

        response = self.assign(self.admin, uuid4())

        # USER_NOT_EXIST — status depends on your UserAccountError.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_uid_returns_invalid(self):
        response = self.assign(self.admin, self.target.id, uid="")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_string_uid_returns_invalid(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url(self.target.id), {"uid": 12345}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_uid_claimed_by_other_user_returns_conflict(self):
        UserNfcCard.objects.create(user=self.regular, uid="CLAIMED")

        response = self.assign(self.admin, self.target.id, uid="CLAIMED")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reassigning_replaces_old_card(self):
        first = UserNfcCard.objects.create(user=self.target, uid="OLD123")

        response = self.assign(self.admin, self.target.id, uid="NEW456")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(UserNfcCard.objects.filter(pk=first.pk).exists())
        self.assertTrue(
            UserNfcCard.objects.filter(user=self.target, uid="NEW456").exists()
        )

    def test_permission_denied_does_not_mutate_db(self):
        existing = UserNfcCard.objects.create(user=self.target, uid="EXISTING")

        response = self.assign(self.regular, self.target.id, uid="HACK")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        existing.refresh_from_db()
        self.assertEqual(existing.uid, "EXISTING")
