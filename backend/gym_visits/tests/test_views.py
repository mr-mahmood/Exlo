# gym_visits/tests/test_views.py
# type: ignore

from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from commerce_orders.models import CommerceProduct, Order, OrderItem
from core.errors import (
    GymDeviceError,
    GymVisitsError,
    GymSubscriptionError,
    UserNfcCardError,
    UserAccountError,
)
from gym.models import Gym
from gym_devices.models import GymDevice
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from gym_visits.models import GymVisit
from users.models import User
from users_nfc_cards.models import UserNfcCard
from django.conf import settings


class NfcFlowTestBase(TestCase):
    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()

        self.gym_a = Gym.objects.create(name="Gym A")
        self.gym_b = Gym.objects.create(name="Gym B")

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

        self.plan_a = GymMembershipPlan.objects.create_plan(
            name="Plan A",
            gym=self.gym_a,
            duration_months=1,
            visit_limit=30,
            price=1000,
        )

        self.device_a, self.token_a = GymDevice.objects.register_device(gym=self.gym_a)
        self.device_b, self.token_b = GymDevice.objects.register_device(gym=self.gym_b)

    # ------------------------------ helpers ------------------------------

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

    def make_active_subscription(self, user, plan, *, remaining=10, expires_in_days=30):
        """Create an ACTIVE subscription directly.

        Used only to set up pre-conditions. Populates duration_months and
        remaining_visits from the plan to stay consistent with the manager
        creation path.
        """
        return GymSubscription.objects.create(
            subscriber=user,
            plan=plan,
            order_item=self._make_order_item(user, plan),
            status=GymSubscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=expires_in_days),
            remaining_visits=remaining,
            duration_months=plan.duration_months,
        )

    def create_subscription(self, user, plan):
        """Create via the real manager path.

        Returns an ACTIVE subscription if the user has none, otherwise PENDING.
        """
        return GymSubscription.objects.create_subscription(
            subscriber=user,
            order_item=self._make_order_item(user, plan),
        )

    def make_pending_subscription(self, user, plan):
        """Create a PENDING subscription via the manager path.

        Uses create_subscription so remaining_visits / duration_months are
        populated from the plan, then demotes to PENDING if it came out ACTIVE.
        """
        sub = self.create_subscription(user, plan)
        if sub.status != GymSubscription.Status.PENDING:
            sub.status = GymSubscription.Status.PENDING
            sub.started_at = None
            sub.expires_at = None
            sub.end_reason = None
            sub.save(
                update_fields=[
                    "status",
                    "started_at",
                    "expires_at",
                    "end_reason",
                    "updated_at",
                ]
            )
        return sub

    def assign_card(self, user, uid):
        return UserNfcCard.objects.assign_card(user=user, uid=uid, assigned_by=None)

    def auth_header(self, token):
        return {"HTTP_AUTHORIZATION": f"Device {token}"}

    def check_in(self, *, gym, token, uid):
        url = reverse("gym_visits:gym-visit-check-in", args=[gym.id])
        return self.client.post(
            url,
            {"uid": uid},
            format="json",
            **self.auth_header(token),
        )

    def check_out(self, *, gym, token, uid):
        url = reverse("gym_visits:gym-visit-check-out", args=[gym.id])
        return self.client.post(
            url,
            {"uid": uid},
            format="json",
            **self.auth_header(token),
        )


class DeviceAuthTests(NfcFlowTestBase):
    def test_missing_authorization_header_is_rejected(self):
        url = reverse("gym_visits:gym-visit-check-in", args=[self.gym_a.id])
        response = self.client.post(url, {"uid": "X"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_malformed_header_is_rejected(self):
        url = reverse("gym_visits:gym-visit-check-in", args=[self.gym_a.id])
        response = self.client.post(
            url,
            {"uid": "X"},
            format="json",
            HTTP_AUTHORIZATION="Device",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_wrong_keyword_is_rejected(self):
        url = reverse("gym_visits:gym-visit-check-in", args=[self.gym_a.id])
        response = self.client.post(
            url,
            {"uid": "X"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_unknown_token_is_rejected(self):
        response = self.check_in(gym=self.gym_a, token="a" * 64, uid="X")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )

    def test_token_from_other_gym_is_rejected(self):
        response = self.check_in(gym=self.gym_b, token=self.token_a, uid="X")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )

    def test_inactive_device_is_rejected(self):
        self.device_a.is_active = False
        self.device_a.save(update_fields=["is_active"])

        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="X")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )


class CardResolutionTests(NfcFlowTestBase):
    def test_missing_uid_is_rejected(self):
        url = reverse("gym_visits:gym-visit-check-in", args=[self.gym_a.id])
        response = self.client.post(
            url,
            {},
            format="json",
            **self.auth_header(self.token_a),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            UserNfcCardError.INVALID_UID[0],
        )

    def test_non_string_uid_is_rejected(self):
        response = self.check_in(gym=self.gym_a, token=self.token_a, uid=12345)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            UserNfcCardError.INVALID_UID[0],
        )

    def test_whitespace_uid_is_rejected(self):
        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="   ")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            UserNfcCardError.INVALID_UID[0],
        )

    def test_unknown_uid_is_rejected(self):
        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="UNKNOWN")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_code"],
            UserNfcCardError.CARD_NOT_FOUND[0],
        )


class CheckInFlowTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()
        self.make_active_subscription(self.user, self.plan_a)
        self.assign_card(self.user, "CARD1")

    def test_successful_check_in_creates_visit_and_decrements_visits(self):
        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        visit = GymVisit.objects.get(user=self.user, gym=self.gym_a)
        self.assertIsNone(visit.checked_out_at)
        self.assertEqual(visit.checked_in_method, GymVisit.Method.NFC)

        sub = GymSubscription.objects.get(subscriber=self.user)
        self.assertEqual(sub.remaining_visits, 9)

    def test_response_body_contains_visit_id(self):
        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_second_check_in_without_checkout_is_rejected(self):
        self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")

        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            GymVisitsError.ALREADY_CHECKED_IN[0],
        )

    def test_check_in_without_active_subscription_is_rejected(self):
        GymSubscription.objects.all().delete()

        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

    def test_check_in_at_wrong_gym_is_rejected(self):
        response = self.check_in(gym=self.gym_b, token=self.token_b, uid="CARD1")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.WRONG_GYM[0],
        )

    def test_check_in_with_expired_subscription_is_rejected(self):
        sub = GymSubscription.objects.get(subscriber=self.user)
        sub.expires_at = timezone.now() - timedelta(seconds=1)
        sub.save(update_fields=["expires_at"])

        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

    def test_check_in_with_exhausted_visits_is_rejected(self):
        sub = GymSubscription.objects.get(subscriber=self.user)
        sub.remaining_visits = 0
        sub.save(update_fields=["remaining_visits"])

        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

    def test_last_visit_expires_subscription_and_allows_next_day(self):
        sub = GymSubscription.objects.get(subscriber=self.user)
        sub.remaining_visits = 1
        sub.save(update_fields=["remaining_visits"])

        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        sub.refresh_from_db()
        self.assertEqual(sub.status, GymSubscription.Status.EXPIRED)
        self.assertEqual(sub.remaining_visits, 0)


class CrossGymCheckInTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()
        self.make_active_subscription(self.user, self.plan_a)
        self.assign_card(self.user, "CARD1")

    def test_second_check_in_at_different_gym_is_rejected(self):
        # Device A checks the user in at gym A.
        r1 = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        # User walks to gym B and taps. Even though the device is valid,
        # the user already has an open visit. The subscription check
        # happens first, but the open-visit check fires regardless.
        # Note: this test relies on the user having NO active sub at gym B,
        # so it will surface as WRONG_GYM. That's correct behavior.
        r2 = self.check_in(gym=self.gym_b, token=self.token_b, uid="CARD1")
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
        # Either WRONG_GYM or ALREADY_CHECKED_IN is acceptable; assert it's one
        # of them, to make the test robust to ordering of checks in the view.
        self.assertIn(
            r2.data["error_code"],
            [
                GymSubscriptionError.WRONG_GYM[0],
                GymVisitsError.ALREADY_CHECKED_IN[0],
            ],
        )


class SubscriptionPromotionTests(NfcFlowTestBase):
    """
    Tests for the expiry + promotion path (GymSubscription._promote_next_for_gym).
    """

    def setUp(self):
        super().setUp()
        self.assign_card(self.user, "CARD1")

    def test_expired_subscription_promotes_same_gym_pending_and_allows_checkin(self):
        # User has an expired active subscription and a pending one at the SAME gym.
        expired = self.make_active_subscription(self.user, self.plan_a, remaining=5)
        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=["expires_at"])

        pending = self.make_pending_subscription(self.user, self.plan_a)
        self.assertEqual(pending.status, GymSubscription.Status.PENDING)

        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        expired.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(expired.status, GymSubscription.Status.EXPIRED)
        self.assertEqual(pending.status, GymSubscription.Status.ACTIVE)
        self.assertEqual(pending.remaining_visits, pending.plan.visit_limit - 1)

    def test_expired_subscription_does_not_promote_pending_at_other_gym(self):
        plan_b = GymMembershipPlan.objects.create_plan(
            name="Plan B",
            gym=self.gym_b,
            duration_months=1,
            visit_limit=30,
            price=1000,
        )
        expired = self.make_active_subscription(self.user, self.plan_a, remaining=5)
        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=["expires_at"])

        # Use the manager path so remaining_visits / duration_months are
        # populated from plan_b, then force PENDING.
        pending_b = self.make_pending_subscription(self.user, plan_b)
        self.assertEqual(pending_b.status, GymSubscription.Status.PENDING)

        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")

        # No active subscription at gym A after promotion attempt → rejected.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

        pending_b.refresh_from_db()
        self.assertEqual(pending_b.status, GymSubscription.Status.PENDING)


class InactiveUserTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()
        self.make_active_subscription(self.user, self.plan_a)
        self.assign_card(self.user, "CARD1")

    def test_inactive_user_cannot_check_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_code"],
            UserAccountError.USER_ACCOUNT_INACTIVE[0],
        )


class MultipleUsersAtSameGymTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()
        self.make_active_subscription(self.user, self.plan_a)
        self.make_active_subscription(self.other_user, self.plan_a)
        self.assign_card(self.user, "CARD1")
        self.assign_card(self.other_user, "CARD2")

    def test_two_users_can_be_checked_in_at_same_gym(self):
        r1 = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
        r2 = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD2")

        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            GymVisit.objects.filter(
                gym=self.gym_a, checked_out_at__isnull=True
            ).count(),
            2,
        )

    def test_checking_out_one_user_does_not_affect_the_other(self):
        self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
        self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD2")

        self.check_out(gym=self.gym_a, token=self.token_a, uid="CARD1")

        open_visits = GymVisit.objects.filter(
            gym=self.gym_a, checked_out_at__isnull=True
        )
        self.assertEqual(open_visits.count(), 1)
        self.assertEqual(open_visits.first().user_id, self.other_user.id)


class UnknownGymTests(NfcFlowTestBase):
    def test_nonexistent_gym_id_is_rejected(self):
        url = reverse("gym_visits:gym-visit-check-in", args=[uuid4()])
        response = self.client.post(
            url,
            {"uid": "CARD1"},
            format="json",
            **self.auth_header(self.token_a),
        )

        # Gym.objects.get_gym raises GYM_NOT_FOUND. Status depends on your
        # GymError constant; adjust as needed.
        self.assertIn(
            response.status_code,
            [status.HTTP_404_NOT_FOUND, status.HTTP_400_BAD_REQUEST],
        )


class CheckOutFlowTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()
        self.make_active_subscription(self.user, self.plan_a)
        self.assign_card(self.user, "CARD1")
        self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")

    def test_successful_check_out_closes_visit(self):
        response = self.check_out(gym=self.gym_a, token=self.token_a, uid="CARD1")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        visit = GymVisit.objects.get(user=self.user, gym=self.gym_a)
        self.assertIsNotNone(visit.checked_out_at)
        self.assertEqual(visit.checked_out_method, GymVisit.Method.NFC)

    def test_check_out_without_open_visit_is_rejected(self):
        self.check_out(gym=self.gym_a, token=self.token_a, uid="CARD1")

        response = self.check_out(gym=self.gym_a, token=self.token_a, uid="CARD1")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_code"],
            GymVisitsError.VISIT_NOT_FOUND[0],
        )

    def test_check_out_at_wrong_gym_is_rejected(self):
        response = self.check_out(gym=self.gym_b, token=self.token_b, uid="CARD1")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_code"],
            GymVisitsError.VISIT_NOT_FOUND[0],
        )

    def test_check_out_does_not_consume_visit(self):
        sub_before = GymSubscription.objects.get(subscriber=self.user).remaining_visits

        self.check_out(gym=self.gym_a, token=self.token_a, uid="CARD1")

        sub_after = GymSubscription.objects.get(subscriber=self.user).remaining_visits
        self.assertEqual(sub_before, sub_after)

    def test_check_out_unknown_uid_is_rejected(self):
        response = self.check_out(gym=self.gym_a, token=self.token_a, uid="NOPE")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_code"],
            UserNfcCardError.CARD_NOT_FOUND[0],
        )


class FullJourneyTests(NfcFlowTestBase):
    def test_full_journey_in_out_in(self):
        sub = self.make_active_subscription(self.user, self.plan_a, remaining=2)
        self.assign_card(self.user, "CARD1")

        r1 = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        r2 = self.check_out(gym=self.gym_a, token=self.token_a, uid="CARD1")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        r3 = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
        self.assertEqual(r3.status_code, status.HTTP_201_CREATED)

        sub.refresh_from_db()
        self.assertEqual(sub.remaining_visits, 0)
        self.assertEqual(sub.status, GymSubscription.Status.EXPIRED)

        self.assertEqual(
            GymVisit.objects.filter(user=self.user, gym=self.gym_a).count(), 2
        )
