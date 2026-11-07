# users_nfc_cards/tests/test_permissions.py

from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from commerce_orders.models import CommerceProduct, Order, OrderItem
from gym.models import Gym
from gym_auth.models import UserGymRole
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User
from users_nfc_cards.permissions import CanAssignUserNfcCard


class PermissionTestBase(TestCase):
    def setUp(self):

        self.gym_a = Gym.objects.create(name="Gym A")
        self.gym_b = Gym.objects.create(name="Gym B")

        self.admin = User.objects.create_superuser(
            phone_number="09120000010",
            password="x",
            first_name="A",
            last_name="D",
            role=User.Role.ADMIN,
        )

        self.owner_a = User.objects.create_user(
            phone_number="09120000011",
            password="x",
            first_name="O",
            last_name="A",
        )

        self.staff_a = User.objects.create_user(
            phone_number="09120000012",
            password="x",
            first_name="S",
            last_name="A",
        )

        self.owner_b = User.objects.create_user(
            phone_number="09120000013",
            password="x",
            first_name="O",
            last_name="B",
        )

        self.regular = User.objects.create_user(
            phone_number="09120000014",
            password="x",
            first_name="R",
            last_name="R",
        )

        self.target = User.objects.create_user(
            phone_number="09120000015",
            password="x",
            first_name="T",
            last_name="T",
        )

        UserGymRole.objects.create(
            user=self.owner_a,
            gym=self.gym_a,
            role=UserGymRole.Role.OWNER,
        )

        UserGymRole.objects.create(
            user=self.staff_a,
            gym=self.gym_a,
            role=UserGymRole.Role.STAFF,
        )

        UserGymRole.objects.create(
            user=self.owner_b,
            gym=self.gym_b,
            role=UserGymRole.Role.OWNER,
        )

        self.plan_a = GymMembershipPlan.objects.create_plan(
            name="Plan A",
            gym=self.gym_a,
            duration_months=1,
            visit_limit=30,
            price=1000,
        )

        self.plan_b = GymMembershipPlan.objects.create_plan(
            name="Plan B",
            gym=self.gym_b,
            duration_months=1,
            visit_limit=30,
            price=1000,
        )

        self.factory = APIRequestFactory()

    def make_request(self, user):
        request = self.factory.post("/")
        request.user = user
        return request

    def call_permission(self, caller, target, gym_id=None):
        request = self.make_request(caller)

        if gym_id is None:
            gym_id = self.gym_a.id

        view = type(
            "V",
            (),
            {
                "kwargs": {
                    "gym_id": gym_id,
                }
            },
        )()

        perm = CanAssignUserNfcCard()

        return perm.has_permission(request, view)

    def create_active_subscription(self, user, plan):
        return GymSubscription.objects.create_subscription(
            subscriber=user,
            order_item=self._make_order_item(user, plan),
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


class HasPermissionTests(PermissionTestBase):
    def test_anonymous_is_rejected(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.make_request(AnonymousUser())

        perm = CanAssignUserNfcCard()

        view = type(
            "V",
            (),
            {
                "kwargs": {
                    "gym_id": self.gym_a.id,
                }
            },
        )()

        self.assertFalse(perm.has_permission(request, view))

    def test_inactive_user_is_rejected(self):
        self.owner_a.is_active = False
        self.owner_a.save(update_fields=["is_active"])

        request = self.make_request(self.owner_a)

        perm = CanAssignUserNfcCard()

        view = type(
            "V",
            (),
            {
                "kwargs": {
                    "gym_id": self.gym_a.id,
                }
            },
        )()

        self.assertFalse(perm.has_permission(request, view))

    def test_active_user_passes_gate(self):
        request = self.make_request(self.owner_a)

        perm = CanAssignUserNfcCard()

        view = type(
            "V",
            (),
            {
                "kwargs": {
                    "gym_id": self.gym_a.id,
                }
            },
        )()

        self.assertTrue(perm.has_permission(request, view))


class HasObjectPermissionTests(PermissionTestBase):
    def test_admin_can_assign_to_member_of_matching_gym(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        self.assertTrue(
            self.call_permission(
                self.admin,
                self.target,
                self.gym_a.id,
            )
        )

    def test_admin_permission_does_not_depend_on_target_subscription(self):
        self.assertTrue(
            self.call_permission(
                self.admin,
                self.target,
                self.gym_a.id,
            )
        )

    def test_admin_permission_does_not_depend_on_target_subscription_gym(self):
        self.create_active_subscription(
            self.target,
            self.plan_b,
        )

        self.assertTrue(
            self.call_permission(
                self.admin,
                self.target,
                self.gym_a.id,
            )
        )

    def test_owner_of_matching_gym_can_assign(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        self.assertTrue(
            self.call_permission(
                self.owner_a,
                self.target,
                self.gym_a.id,
            )
        )

    def test_staff_of_matching_gym_can_assign(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        self.assertTrue(
            self.call_permission(
                self.staff_a,
                self.target,
                self.gym_a.id,
            )
        )

    def test_owner_of_other_gym_cannot_assign(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        self.assertFalse(
            self.call_permission(
                self.owner_b,
                self.target,
                self.gym_a.id,
            )
        )

    def test_user_with_no_gym_roles_cannot_assign(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        self.assertFalse(
            self.call_permission(
                self.regular,
                self.target,
                self.gym_a.id,
            )
        )

    def test_owner_permission_does_not_depend_on_target_subscription(self):
        self.assertTrue(
            self.call_permission(
                self.owner_a,
                self.target,
                self.gym_a.id,
            )
        )

    def test_owner_permission_ignores_expired_target_subscription(self):
        sub = self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        sub.expires_at = timezone.now() - timedelta(seconds=1)
        sub.save(update_fields=["expires_at"])

        self.assertTrue(
            self.call_permission(
                self.owner_a,
                self.target,
                self.gym_a.id,
            )
        )

    def test_owner_permission_ignores_exhausted_target_subscription(self):
        sub = self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        sub.remaining_visits = 0
        sub.save(update_fields=["remaining_visits"])

        self.assertTrue(
            self.call_permission(
                self.owner_a,
                self.target,
                self.gym_a.id,
            )
        )

    def test_owner_permission_ignores_pending_target_subscription(self):
        sub = GymSubscription.objects.create_subscription(
            subscriber=self.target,
            order_item=self._make_order_item(
                self.target,
                self.plan_a,
            ),
        )
        sub.status = GymSubscription.Status.PENDING
        sub.started_at = None
        sub.expires_at = None
        sub.save(update_fields=["status", "started_at", "expires_at"])

        self.assertTrue(
            self.call_permission(
                self.owner_a,
                self.target,
                self.gym_a.id,
            )
        )

    def test_owner_permission_ignores_cancelled_target_subscription(self):
        sub = self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        sub.status = GymSubscription.Status.CANCELLED
        sub.save(update_fields=["status"])

        self.assertTrue(
            self.call_permission(
                self.owner_a,
                self.target,
                self.gym_a.id,
            )
        )

    def test_owner_of_gym_a_cannot_use_gym_b(self):
        self.create_active_subscription(
            self.target,
            self.plan_b,
        )

        self.assertFalse(
            self.call_permission(
                self.owner_a,
                self.target,
                self.gym_b.id,
            )
        )
