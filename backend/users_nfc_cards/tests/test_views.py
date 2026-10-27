# users_nfc_cards/tests/test_views.py


from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from commerce_orders.models import CommerceProduct, Order, OrderItem
from gym.models import Gym
from gym_auth.models import UserGymRole
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User


class ViewTestBase(TestCase):
    def setUp(self):

        cache.clear()

        self.client = APIClient()

        self.gym_a = Gym.objects.create(
            name="Gym A",
        )

        self.gym_b = Gym.objects.create(
            name="Gym B",
        )

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

        self.staff_a = User.objects.create_user(
            phone_number="09120000022",
            password="x",
            first_name="S",
            last_name="A",
        )

        self.regular = User.objects.create_user(
            phone_number="09120000023",
            password="x",
            first_name="R",
            last_name="R",
        )

        self.target = User.objects.create_user(
            phone_number="09120000024",
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

    def tearDown(self):
        cache.clear()

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

    def url(self, gym_id):
        return reverse(
            "users_nfc_cards:assign",
            args=[gym_id],
        )

    def assign_request(self, as_user, gym_id=None, phone=None):
        self.client.force_authenticate(user=as_user)

        if gym_id is None:
            gym_id = self.gym_a.id

        if phone is None:
            phone = self.target.phone_number

        return self.client.post(
            self.url(gym_id),
            {"phone": phone},
            format="json",
        )


class AssignRequestViewTests(ViewTestBase):
    def test_admin_can_create_assignment_request_for_member(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        response = self.assign_request(
            self.admin,
            self.gym_a.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            cache.get(f"nfc_card_assign_{self.gym_a.id}"),
            self.target.pk,
        )

    def test_admin_cannot_create_assignment_request_for_non_member(self):
        response = self.assign_request(
            self.admin,
            self.gym_a.id,
        )

        self.assertNotEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertIsNone(cache.get(f"nfc_card_assign_{self.gym_a.id}"))

    def test_owner_can_create_assignment_request_for_member(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        response = self.assign_request(
            self.owner_a,
            self.gym_a.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            cache.get(f"nfc_card_assign_{self.gym_a.id}"),
            self.target.pk,
        )

    def test_staff_can_create_assignment_request_for_member(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        response = self.assign_request(
            self.staff_a,
            self.gym_a.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_owner_cannot_create_request_for_non_member(self):
        response = self.assign_request(
            self.owner_a,
            self.gym_a.id,
        )

        self.assertNotEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertIsNone(cache.get(f"nfc_card_assign_{self.gym_a.id}"))

    def test_regular_user_cannot_create_assignment_request(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        response = self.assign_request(
            self.regular,
            self.gym_a.id,
        )

        self.assertNotEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertIsNone(cache.get(f"nfc_card_assign_{self.gym_a.id}"))

    def test_anonymous_cannot_create_assignment_request(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.url(self.gym_a.id),
            {
                "phone": self.target.phone_number,
            },
            format="json",
        )

        self.assertNotEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_target_user_does_not_exist(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url(self.gym_a.id),
            {
                "phone": "09129999999",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_missing_phone_is_rejected(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url(self.gym_a.id),
            {},
            format="json",
        )

        self.assertNotEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_invalid_phone_is_rejected(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url(self.gym_a.id),
            {
                "phone": "invalid",
            },
            format="json",
        )

        self.assertNotEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_second_request_for_same_gym_is_rejected(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        first_response = self.assign_request(
            self.admin,
            self.gym_a.id,
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_201_CREATED,
        )

        second_user = User.objects.create_user(
            phone_number="09120000025",
            password="x",
            first_name="Second",
            last_name="User",
        )

        self.create_active_subscription(
            second_user,
            self.plan_a,
        )

        second_response = self.assign_request(
            self.admin,
            self.gym_a.id,
            phone=second_user.phone_number,
        )

        self.assertNotEqual(
            second_response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            cache.get(f"nfc_card_assign_{self.gym_a.id}"),
            self.target.pk,
        )

    def test_different_gyms_can_have_separate_pending_requests(self):
        target_b = User.objects.create_user(
            phone_number="09120000026",
            password="x",
            first_name="Target",
            last_name="B",
        )

        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        self.create_active_subscription(
            target_b,
            self.plan_b,
        )

        response_a = self.assign_request(
            self.admin,
            self.gym_a.id,
            self.target.phone_number,
        )

        response_b = self.assign_request(
            self.admin,
            self.gym_b.id,
            target_b.phone_number,
        )

        self.assertEqual(
            response_a.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response_b.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            cache.get(f"nfc_card_assign_{self.gym_a.id}"),
            self.target.pk,
        )

        self.assertEqual(
            cache.get(f"nfc_card_assign_{self.gym_b.id}"),
            target_b.pk,
        )

    def test_request_does_not_create_nfc_card_immediately(self):
        self.create_active_subscription(
            self.target,
            self.plan_a,
        )

        response = self.assign_request(
            self.admin,
            self.gym_a.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertFalse(
            User.objects.filter(
                pk=self.target.pk,
                nfc_card__isnull=False,
            ).exists()
        )
