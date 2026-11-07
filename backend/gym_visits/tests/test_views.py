# gym_visits/tests/test_views.py


from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from uuid import uuid7
from django.core.cache import cache
from django.db import DatabaseError, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from commerce_orders.models import CommerceProduct, Order, OrderItem
from core.errors import (
    APIError,
    GymDeviceError,
    GymVisitsError,
    GymSubscriptionError,
    UserNfcCardError,
    UserAccountError,
    GymLockerError,
)
from core.cache import USER_SUBSCRIPTION, cache_key
from gym.models import Gym
from gym_devices.models import GymDevice
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from gym_visits.models import GymVisit
from users.models import User
from users_nfc_cards.models import UserNfcCard
from gym_locks.models import GymLocker, GymLockerManager


class NfcFlowTestBase(TestCase):
    def setUp(self):
        cache.clear()

        self.client = APIClient()

        self.gym_a = Gym.objects.create(name="Gym A")
        self.gym_b = Gym.objects.create(name="Gym B")

        GymLocker.objects.add_lockers(gym=self.gym_a, count=10)
        GymLocker.objects.add_lockers(gym=self.gym_b, count=10)

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

        self.device_a, self.token_a = GymDevice.objects.register_device(
            gym=self.gym_a,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        self.device_b, self.token_b = GymDevice.objects.register_device(
            gym=self.gym_b,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

    def tearDown(self):
        cache.clear()

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

    def make_active_subscription(
        self,
        user,
        plan,
        *,
        remaining=10,
        expires_in_days=30,
    ):
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
        return GymSubscription.objects.create_subscription(
            subscriber=user,
            order_item=self._make_order_item(user, plan),
        )

    def make_pending_subscription(self, user, plan):
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
        return UserNfcCard.objects.assign_card(
            user=user,
            uid=uid,
        )

    def create_pending_card_assignment(self, gym, user):
        return cache.add(
            f"nfc_card_assign_{gym.id}",
            user.pk,
            timeout=5 * 60,
        )

    def auth_header(self, token):
        return {
            "HTTP_AUTHORIZATION": f"Device {token}",
        }

    def check_in(self, *, gym, token, uid):
        url = reverse(
            "gym_visits:gym-visit-check-in",
            args=[gym.id],
        )

        return self.client.post(
            url,
            {"uid": uid},
            format="json",
            **self.auth_header(token),
        )

    def check_out(self, *, gym, token, uid):
        url = reverse(
            "gym_visits:gym-visit-check-out",
            args=[gym.id],
        )

        return self.client.post(
            url,
            {"uid": uid},
            format="json",
            **self.auth_header(token),
        )


class DeviceAuthTests(NfcFlowTestBase):
    def test_missing_authorization_header_is_rejected(self):
        url = reverse(
            "gym_visits:gym-visit-check-in",
            args=[self.gym_a.id],
        )

        response = self.client.post(
            url,
            {"uid": "X"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_malformed_header_is_rejected(self):
        url = reverse(
            "gym_visits:gym-visit-check-in",
            args=[self.gym_a.id],
        )

        response = self.client.post(
            url,
            {"uid": "X"},
            format="json",
            HTTP_AUTHORIZATION="Device",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_wrong_keyword_is_rejected(self):
        url = reverse(
            "gym_visits:gym-visit-check-in",
            args=[self.gym_a.id],
        )

        response = self.client.post(
            url,
            {"uid": "X"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_unknown_token_is_rejected(self):
        response = self.check_in(
            gym=self.gym_a,
            token="a" * 64,
            uid="X",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )

    def test_token_from_other_gym_is_rejected(self):
        response = self.check_in(
            gym=self.gym_b,
            token=self.token_a,
            uid="X",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )

    def test_inactive_device_is_rejected(self):
        self.device_a.is_active = False
        self.device_a.save(update_fields=["is_active"])

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="X",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )


class CardResolutionTests(NfcFlowTestBase):
    def test_missing_uid_is_rejected(self):
        url = reverse(
            "gym_visits:gym-visit-check-in",
            args=[self.gym_a.id],
        )

        response = self.client.post(
            url,
            {},
            format="json",
            **self.auth_header(self.token_a),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data["error_code"],
            UserNfcCardError.INVALID_UID[0],
        )

    def test_whitespace_uid_is_rejected(self):
        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="   ",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data["error_code"],
            UserNfcCardError.INVALID_UID[0],
        )

    def test_unknown_uid_without_pending_assignment_is_rejected(self):
        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="UNKNOWN",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            response.data["error_code"],
            UserNfcCardError.CARD_NOT_FOUND[0],
        )

    def test_existing_card_is_resolved_normally(self):
        self.make_active_subscription(
            self.user,
            self.plan_a,
        )
        self.assign_card(
            self.user,
            "CARD1",
        )

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )


class NewCardAssignmentFlowTests(NfcFlowTestBase):
    def test_unassigned_card_with_pending_assignment_is_assigned(self):
        self.make_active_subscription(
            self.user,
            self.plan_a,
        )

        self.assertTrue(
            self.create_pending_card_assignment(
                self.gym_a,
                self.user,
            )
        )

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="NEW_CARD",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertTrue(
            UserNfcCard.objects.filter(
                user=self.user,
                uid="NEW_CARD",
            ).exists()
        )

    def test_card_assignment_does_not_create_visit(self):
        self.make_active_subscription(
            self.user,
            self.plan_a,
            remaining=10,
        )

        self.create_pending_card_assignment(
            self.gym_a,
            self.user,
        )

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="NEW_CARD",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertFalse(
            GymVisit.objects.filter(
                user=self.user,
                gym=self.gym_a,
            ).exists()
        )

        sub = GymSubscription.objects.get(
            subscriber=self.user,
        )

        self.assertEqual(
            sub.remaining_visits,
            10,
        )

    def test_card_assignment_consumes_pending_request(self):
        self.make_active_subscription(
            self.user,
            self.plan_a,
        )

        key = f"nfc_card_assign_{self.gym_a.id}"

        self.assertTrue(
            self.create_pending_card_assignment(
                self.gym_a,
                self.user,
            )
        )

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="NEW_CARD",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertIsNone(cache.get(key))

    def test_card_assignment_replaces_existing_card(self):
        self.make_active_subscription(
            self.user,
            self.plan_a,
        )

        old_card = self.assign_card(
            self.user,
            "OLD_CARD",
        )

        self.create_pending_card_assignment(
            self.gym_a,
            self.user,
        )

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="NEW_CARD",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertFalse(
            UserNfcCard.objects.filter(
                pk=old_card.pk,
            ).exists()
        )

        self.assertTrue(
            UserNfcCard.objects.filter(
                user=self.user,
                uid="NEW_CARD",
            ).exists()
        )

    def test_existing_uid_is_not_reassigned_to_pending_user(self):
        self.assign_card(
            self.other_user,
            "EXISTING_CARD",
        )

        self.create_pending_card_assignment(
            self.gym_a,
            self.user,
        )

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="EXISTING_CARD",
        )

        self.assertNotEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        card = UserNfcCard.objects.get(
            uid="EXISTING_CARD",
        )

        self.assertEqual(
            card.user_id,
            self.other_user.id,
        )

        self.assertEqual(
            cache.get(f"nfc_card_assign_{self.gym_a.id}"),
            self.user.pk,
        )

    def test_new_card_requires_second_scan_to_check_in(self):
        self.make_active_subscription(
            self.user,
            self.plan_a,
            remaining=10,
        )

        self.create_pending_card_assignment(
            self.gym_a,
            self.user,
        )

        assignment_response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="NEW_CARD",
        )

        self.assertEqual(
            assignment_response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            GymVisit.objects.filter(
                user=self.user,
                gym=self.gym_a,
            ).count(),
            0,
        )

        check_in_response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="NEW_CARD",
        )

        self.assertEqual(
            check_in_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            GymVisit.objects.filter(
                user=self.user,
                gym=self.gym_a,
            ).count(),
            1,
        )

        sub = GymSubscription.objects.get(
            subscriber=self.user,
        )

        self.assertEqual(
            sub.remaining_visits,
            9,
        )


class CheckInFlowTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()

        self.make_active_subscription(
            self.user,
            self.plan_a,
        )

        self.assign_card(
            self.user,
            "CARD1",
        )

    def test_successful_check_in_creates_visit_and_decrements_visits(self):
        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertTrue(
            GymLocker.objects.filter(
                gym=self.gym_a,
                assigned_user=self.user,
                is_active=True,
            ).exists()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        visit: GymVisit = GymVisit.objects.get(
            user=self.user,
            gym=self.gym_a,
        )

        self.assertIsNone(
            visit.checked_out_at,
        )

        self.assertEqual(
            visit.checked_in_method,
            GymVisit.Method.NFC,
        )

        sub: GymSubscription = GymSubscription.objects.get(
            subscriber=self.user,
        )

        self.assertEqual(
            sub.remaining_visits,
            9,
        )

    def test_second_check_in_without_checkout_is_rejected(self):
        self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["error_code"],
            GymVisitsError.ALREADY_CHECKED_IN[0],
        )
        self.assertEqual(GymVisit.objects.filter(user=self.user).count(), 1)
        self.assertEqual(
            GymSubscription.objects.get(subscriber=self.user).remaining_visits, 9
        )

    def test_check_in_without_active_subscription_is_rejected(self):
        GymSubscription.objects.all().delete()

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

    def test_check_in_at_wrong_gym_is_rejected(self):
        response = self.check_in(
            gym=self.gym_b,
            token=self.token_b,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

    def test_check_in_with_expired_subscription_is_rejected(self):
        sub: GymSubscription = GymSubscription.objects.get(
            subscriber=self.user,
        )

        sub.expires_at = timezone.now() - timedelta(seconds=1)
        sub.save(update_fields=["expires_at"])

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

        sub.refresh_from_db()
        self.assertEqual(sub.status, GymSubscription.Status.EXPIRED)
        self.assertEqual(sub.end_reason, GymSubscription.EndReason.TIME)
        self.assertEqual(sub.remaining_visits, 10)
        self.assertFalse(GymVisit.objects.filter(user=self.user).exists())

    def test_check_in_with_exhausted_visits_is_rejected(self):
        sub = GymSubscription.objects.get(
            subscriber=self.user,
        )

        sub.remaining_visits = 0
        sub.save(update_fields=["remaining_visits"])

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

    def test_last_visit_expires_subscription(self):
        sub = GymSubscription.objects.get(
            subscriber=self.user,
        )

        sub.remaining_visits = 1
        sub.save(update_fields=["remaining_visits"])

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        sub.refresh_from_db()

        self.assertEqual(
            sub.status,
            GymSubscription.Status.EXPIRED,
        )

        self.assertEqual(
            sub.remaining_visits,
            0,
        )

    def test_check_in_rolls_back_when_no_locker_is_available(self):
        GymLocker.objects.filter(gym=self.gym_a).update(is_active=False)

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertFalse(
            GymVisit.objects.filter(
                user=self.user,
                gym=self.gym_a,
            ).exists()
        )

        sub = GymSubscription.objects.get(subscriber=self.user)
        self.assertEqual(sub.remaining_visits, 10)
        self.assertFalse(
            GymLocker.objects.filter(gym=self.gym_a, assigned_user=self.user).exists()
        )


class CrossGymCheckInTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()

        self.make_active_subscription(
            self.user,
            self.plan_a,
        )

        self.assign_card(
            self.user,
            "CARD1",
        )

    def test_check_in_at_different_gym_is_rejected(self):
        response = self.check_in(
            gym=self.gym_b,
            token=self.token_b,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

    def test_open_visit_blocks_check_in_at_other_gym(self):
        plan_b = GymMembershipPlan.objects.create_plan(
            name="Plan B",
            gym=self.gym_b,
            duration_months=1,
            visit_limit=30,
            price=1000,
        )
        gym_b_subscription = self.make_active_subscription(self.user, plan_b)
        self.assertEqual(
            self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1").status_code,
            200,
        )

        response = self.check_in(gym=self.gym_b, token=self.token_b, uid="CARD1")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["error_code"], GymVisitsError.ALREADY_CHECKED_IN[0]
        )
        gym_b_subscription.refresh_from_db()
        self.assertEqual(gym_b_subscription.remaining_visits, 10)
        self.assertEqual(GymVisit.objects.filter(user=self.user).count(), 1)


class SubscriptionPromotionTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()

        self.assign_card(
            self.user,
            "CARD1",
        )

    def make_plan_b(self):
        return GymMembershipPlan.objects.create_plan(
            name="Plan B",
            gym=self.gym_b,
            duration_months=1,
            visit_limit=30,
            price=1000,
        )

    def assert_subscription_api_states(self, *expected):
        client = APIClient()
        client.force_authenticate(user=self.user)
        for subscription, expected_status in expected:
            response = client.get(
                reverse(
                    "gym_subscriptions:gym-subscription-detail",
                    kwargs={"subscription_id": subscription.pk},
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["data"]["subscription"]["status"], expected_status
            )
        response = client.get(reverse("gym_subscriptions:gym-subscription-list"))
        self.assertEqual(response.status_code, 200)
        states = {
            subscription["id"]: subscription["status"]
            for subscription in response.json()["data"]["subscriptions"]
        }
        for subscription, expected_status in expected:
            self.assertEqual(states[str(subscription.pk)], expected_status)

    def test_last_visit_promotes_same_gym_and_preserves_other_gym_queue(self):
        active = self.make_active_subscription(self.user, self.plan_a, remaining=1)
        pending_b = self.make_pending_subscription(self.user, self.make_plan_b())
        later_a = self.make_pending_subscription(self.user, self.plan_a)
        self.assert_subscription_api_states(
            (active, "ACTIVE"), (pending_b, "PENDING"), (later_a, "PENDING")
        )
        keys = {
            sub.pk: cache_key(USER_SUBSCRIPTION, self.user.pk, sub.pk)
            for sub in (active, pending_b)
        }

        with self.captureOnCommitCallbacks(execute=True):
            response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
            self.assertEqual(response.status_code, 200)
            for sub_id, key in keys.items():
                self.assertEqual(
                    cache_key(USER_SUBSCRIPTION, self.user.pk, sub_id), key
                )

        active.refresh_from_db()
        pending_b.refresh_from_db()
        later_a.refresh_from_db()
        self.assertEqual(active.status, "EXPIRED")
        self.assertEqual(active.end_reason, "VISITS")
        self.assertEqual(active.remaining_visits, 0)
        self.assertEqual(pending_b.status, "PENDING")
        self.assertEqual(pending_b.remaining_visits, 30)
        self.assertEqual(later_a.status, "ACTIVE")
        visit = GymVisit.objects.get(user=self.user)
        self.assertEqual(visit.gym_id, self.gym_a.pk)
        self.assertEqual(visit.subscription_id, active.pk)
        self.assert_subscription_api_states(
            (active, "EXPIRED"), (pending_b, "PENDING"), (later_a, "ACTIVE")
        )

        self.assertEqual(
            self.check_out(gym=self.gym_a, token=self.token_a, uid="CARD1").status_code,
            200,
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.check_in(gym=self.gym_b, token=self.token_b, uid="CARD1")
        self.assertEqual(response.status_code, 200)
        pending_b.refresh_from_db()
        self.assertEqual(pending_b.remaining_visits, 29)
        self.assertEqual(
            GymVisit.objects.get(
                user=self.user, checked_out_at__isnull=True
            ).subscription_id,
            pending_b.pk,
        )

    def test_check_in_recovers_pending_subscription_after_previous_expired(self):
        expired = self.make_active_subscription(self.user, self.plan_a, remaining=0)
        pending_b = self.make_pending_subscription(self.user, self.make_plan_b())
        expired.expire(reason=GymSubscription.EndReason.VISITS)
        self.assert_subscription_api_states(
            (expired, "EXPIRED"), (pending_b, "PENDING")
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.check_in(gym=self.gym_b, token=self.token_b, uid="CARD1")

        self.assertEqual(response.status_code, 200)
        pending_b.refresh_from_db()
        self.assertEqual(pending_b.status, "ACTIVE")
        self.assertEqual(pending_b.remaining_visits, 29)
        self.assertIsNotNone(pending_b.started_at)
        self.assertEqual(
            GymVisit.objects.get(user=self.user, gym=self.gym_b).subscription_id,
            pending_b.pk,
        )
        self.assert_subscription_api_states((expired, "EXPIRED"), (pending_b, "ACTIVE"))

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            retry = self.check_in(gym=self.gym_b, token=self.token_b, uid="CARD1")
        self.assertEqual(retry.status_code, 400)
        self.assertEqual(
            retry.json()["error_code"], GymVisitsError.ALREADY_CHECKED_IN[0]
        )
        self.assertEqual(callbacks, [])
        pending_b.refresh_from_db()
        self.assertEqual(pending_b.remaining_visits, 29)
        self.assertEqual(GymVisit.objects.filter(user=self.user).count(), 1)

    def test_check_in_at_other_gym_does_not_expire_first_gym_subscription(self):
        expired = self.make_active_subscription(
            self.user, self.plan_a, remaining=5, expires_in_days=-1
        )
        pending_b = self.make_pending_subscription(self.user, self.make_plan_b())
        self.assert_subscription_api_states((expired, "ACTIVE"), (pending_b, "PENDING"))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.check_in(gym=self.gym_b, token=self.token_b, uid="CARD1")

        self.assertEqual(response.status_code, 200)
        expired.refresh_from_db()
        self.assertEqual(expired.status, "ACTIVE")
        self.assertIsNone(expired.end_reason)
        self.assertEqual(expired.remaining_visits, 5)
        self.assert_subscription_api_states((expired, "ACTIVE"), (pending_b, "ACTIVE"))

    def test_last_visit_promotion_rolls_back_when_no_locker_is_available(self):
        active = self.make_active_subscription(self.user, self.plan_a, remaining=1)
        pending_b = self.make_pending_subscription(self.user, self.make_plan_b())
        GymLocker.objects.filter(gym=self.gym_a).update(is_active=False)
        self.assert_subscription_api_states((active, "ACTIVE"), (pending_b, "PENDING"))

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error_code"], GymLockerError.NO_AVAILABLE_LOCKER[0]
        )
        self.assertEqual(callbacks, [])
        active.refresh_from_db()
        pending_b.refresh_from_db()
        self.assertEqual(active.status, "ACTIVE")
        self.assertEqual(active.remaining_visits, 1)
        self.assertEqual(pending_b.status, "PENDING")
        self.assertEqual(pending_b.remaining_visits, 30)
        self.assertIsNone(pending_b.started_at)
        self.assertIsNone(pending_b.expires_at)
        self.assertFalse(GymVisit.objects.filter(user=self.user).exists())
        self.assert_subscription_api_states((active, "ACTIVE"), (pending_b, "PENDING"))

    def test_recovery_promotion_rolls_back_when_no_locker_is_available(self):
        expired = self.make_active_subscription(self.user, self.plan_a, remaining=0)
        pending_b = self.make_pending_subscription(self.user, self.make_plan_b())
        expired.expire(reason=GymSubscription.EndReason.VISITS)
        GymLocker.objects.filter(gym=self.gym_b).update(is_active=False)

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.check_in(gym=self.gym_b, token=self.token_b, uid="CARD1")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error_code"], GymLockerError.NO_AVAILABLE_LOCKER[0]
        )
        self.assertEqual(callbacks, [])
        pending_b.refresh_from_db()
        self.assertEqual(pending_b.status, "PENDING")
        self.assertEqual(pending_b.remaining_visits, 30)
        self.assertIsNone(pending_b.started_at)
        self.assertIsNone(pending_b.expires_at)
        self.assertFalse(GymVisit.objects.filter(user=self.user).exists())

    def test_existing_active_subscription_allows_other_gyms_pending_subscription(self):
        active = self.make_active_subscription(self.user, self.plan_a, remaining=10)
        pending_b = self.make_pending_subscription(self.user, self.make_plan_b())
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.check_in(gym=self.gym_b, token=self.token_b, uid="CARD1")
        self.assertEqual(response.status_code, 200)
        active.refresh_from_db()
        pending_b.refresh_from_db()
        self.assertEqual(active.remaining_visits, 10)
        self.assertEqual(pending_b.status, "ACTIVE")
        self.assertEqual(pending_b.remaining_visits, 29)
        self.assertEqual(
            GymVisit.objects.get(user=self.user).subscription_id, pending_b.pk
        )

    def test_expired_subscription_promotes_same_gym_pending_and_allows_checkin(self):
        expired = self.make_active_subscription(
            self.user,
            self.plan_a,
            remaining=5,
        )

        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=["expires_at"])

        pending = self.make_pending_subscription(
            self.user,
            self.plan_a,
        )

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
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

        self.assertEqual(
            pending.remaining_visits,
            pending.plan.visit_limit - 1,
        )
        self.assertEqual(expired.end_reason, GymSubscription.EndReason.TIME)
        self.assertEqual(expired.remaining_visits, 5)
        self.assertEqual(
            GymVisit.objects.get(user=self.user, gym=self.gym_a).subscription_id,
            pending.pk,
        )
        self.assertEqual(GymVisit.objects.filter(user=self.user).count(), 1)

    def test_expired_subscription_does_not_promote_pending_at_other_gym(self):
        plan_b = GymMembershipPlan.objects.create_plan(
            name="Plan B",
            gym=self.gym_b,
            duration_months=1,
            visit_limit=30,
            price=1000,
        )

        expired = self.make_active_subscription(
            self.user,
            self.plan_a,
            remaining=5,
        )

        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=["expires_at"])

        pending_b = self.make_pending_subscription(
            self.user,
            plan_b,
        )

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["error_code"],
            GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0],
        )

        pending_b.refresh_from_db()

        self.assertEqual(
            pending_b.status,
            GymSubscription.Status.PENDING,
        )


class InactiveUserTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()

        self.make_active_subscription(
            self.user,
            self.plan_a,
        )

        self.assign_card(
            self.user,
            "CARD1",
        )

    def test_inactive_user_cannot_check_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["error_code"],
            UserAccountError.USER_ACCOUNT_INACTIVE[0],
        )


class MultipleUsersAtSameGymTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()

        self.make_active_subscription(
            self.user,
            self.plan_a,
        )

        self.make_active_subscription(
            self.other_user,
            self.plan_a,
        )

        self.assign_card(
            self.user,
            "CARD1",
        )

        self.assign_card(
            self.other_user,
            "CARD2",
        )

    def test_two_users_can_be_checked_in_at_same_gym(self):
        r1 = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        r2 = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD2",
        )

        self.assertEqual(
            r1.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            r2.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            GymVisit.objects.filter(
                gym=self.gym_a,
                checked_out_at__isnull=True,
            ).count(),
            2,
        )

    def test_checking_out_one_user_does_not_affect_the_other(self):
        self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD2",
        )

        self.check_out(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        open_visits = GymVisit.objects.filter(
            gym=self.gym_a,
            checked_out_at__isnull=True,
        )

        self.assertEqual(
            open_visits.count(),
            1,
        )

        self.assertEqual(
            open_visits.first().user_id,
            self.other_user.id,
        )


class UnknownGymTests(NfcFlowTestBase):
    def test_nonexistent_gym_id_is_rejected(self):
        url = reverse(
            "gym_visits:gym-visit-check-in",
            args=[uuid7()],
        )

        response = self.client.post(
            url,
            {"uid": "CARD1"},
            format="json",
            **self.auth_header(self.token_a),
        )

        self.assertIn(
            response.status_code,
            [
                status.HTTP_404_NOT_FOUND,
                status.HTTP_400_BAD_REQUEST,
            ],
        )


class CheckOutFlowTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()

        self.make_active_subscription(
            self.user,
            self.plan_a,
        )

        self.assign_card(
            self.user,
            "CARD1",
        )

        self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

    def test_successful_check_out_closes_visit(self):
        response = self.check_out(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertFalse(
            GymLocker.objects.filter(
                gym=self.gym_a,
                assigned_user=self.user,
            ).exists()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        visit: GymVisit = GymVisit.objects.get(
            user=self.user,
            gym=self.gym_a,
        )

        self.assertIsNotNone(
            visit.checked_out_at,
        )

        self.assertEqual(
            visit.checked_out_method,
            GymVisit.Method.NFC,
        )

    def test_expired_subscription_keeps_open_visit_and_locker_access(self):
        visit = GymVisit.objects.get(user=self.user, gym=self.gym_a)
        subscription = visit.subscription
        subscription.expire(GymSubscription.EndReason.TIME)

        locker = GymLocker.objects.get_user_locker(self.gym_a, self.user)
        self.assertEqual(locker.assigned_user_id, self.user.pk)
        self.assertEqual(visit.subscription_id, subscription.pk)

        response = self.check_out(gym=self.gym_a, token=self.token_a, uid="CARD1")
        self.assertEqual(response.status_code, 200)
        visit.refresh_from_db()
        self.assertIsNotNone(visit.checked_out_at)
        subscription.refresh_from_db()
        self.assertEqual(subscription.remaining_visits, 9)

        locker.assigned_user = self.user
        locker.save(update_fields=["assigned_user"])
        with self.assertRaises(APIError):
            GymLocker.objects.get_user_locker(self.gym_a, self.user)

    def test_check_out_without_open_visit_is_rejected(self):
        self.check_out(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        response = self.check_out(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.assertEqual(
            response.data["error_code"],
            GymVisitsError.VISIT_NOT_FOUND[0],
        )

    def test_check_out_at_wrong_gym_is_rejected(self):
        response = self.check_out(
            gym=self.gym_b,
            token=self.token_b,
            uid="CARD1",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.assertEqual(
            response.data["error_code"],
            GymVisitsError.VISIT_NOT_FOUND[0],
        )

    def test_check_out_does_not_consume_visit(self):
        sub_before = GymSubscription.objects.get(
            subscriber=self.user,
        ).remaining_visits

        self.check_out(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        sub_after = GymSubscription.objects.get(
            subscriber=self.user,
        ).remaining_visits

        self.assertEqual(
            sub_before,
            sub_after,
        )

    def test_check_out_unknown_uid_is_rejected(self):
        response = self.check_out(
            gym=self.gym_a,
            token=self.token_a,
            uid="NOPE",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.assertEqual(
            response.data["error_code"],
            UserNfcCardError.CARD_NOT_FOUND[0],
        )


class FullJourneyTests(NfcFlowTestBase):
    def test_full_new_card_journey_assignment_then_in_out_in(self):
        sub = self.make_active_subscription(
            self.user,
            self.plan_a,
            remaining=2,
        )

        # Reception/admin has previously created the temporary
        # assignment request.
        self.assertTrue(
            self.create_pending_card_assignment(
                self.gym_a,
                self.user,
            )
        )

        # First tap: assign card only.
        assignment_response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            assignment_response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            GymVisit.objects.filter(
                user=self.user,
                gym=self.gym_a,
            ).count(),
            0,
        )

        sub.refresh_from_db()

        self.assertEqual(
            sub.remaining_visits,
            2,
        )

        # Second tap: actual check-in.
        check_in_response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            check_in_response.status_code,
            status.HTTP_200_OK,
        )

        sub.refresh_from_db()

        self.assertEqual(
            sub.remaining_visits,
            1,
        )

        # Check out.
        check_out_response = self.check_out(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            check_out_response.status_code,
            status.HTTP_200_OK,
        )

        # Second actual visit.
        second_check_in_response = self.check_in(
            gym=self.gym_a,
            token=self.token_a,
            uid="CARD1",
        )

        self.assertEqual(
            second_check_in_response.status_code,
            status.HTTP_200_OK,
        )

        sub.refresh_from_db()

        self.assertEqual(
            sub.remaining_visits,
            0,
        )

        self.assertEqual(
            sub.status,
            GymSubscription.Status.EXPIRED,
        )

        self.assertEqual(
            GymVisit.objects.filter(
                user=self.user,
                gym=self.gym_a,
            ).count(),
            2,
        )


class CheckInConcurrencyTests(TransactionTestCase):
    def test_concurrent_check_ins_create_one_admission(self):
        gym = Gym.objects.create(name="Gym")
        user = User.objects.create_user(phone_number="09120000001")
        plan = GymMembershipPlan.objects.create_plan(
            name="Plan", gym=gym, duration_months=1, visit_limit=4, price=1000
        )
        order = Order.objects.create(
            buyer=user,
            status=Order.Status.PAID,
            subtotal_amount=1000,
            discount_amount=0,
            tax_amount=0,
            total_amount=1000,
            paid_at=timezone.now(),
        )
        item = OrderItem.objects.create(
            commerce_product=plan.id,
            order=order,
            item_type=CommerceProduct.ProductType.GYM_MEMBERSHIP,
            item_snapshot={},
            quantity=1,
            unit_price=1000,
            subtotal_amount=1000,
            discount_amount=0,
            tax_amount=0,
            total_amount=1000,
        )
        subscription = GymSubscription.objects.create(
            subscriber=user,
            plan=plan,
            order_item=item,
            status=GymSubscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
            remaining_visits=2,
            duration_months=1,
        )
        GymLocker.objects.add_lockers(gym=gym, count=2)
        UserNfcCard.objects.assign_card(user=user, uid="CARD1")
        _, token = GymDevice.objects.register_device(
            gym=gym, device_type=GymDevice.GymDeviceType.ENTRANCE
        )
        url = reverse("gym_visits:gym-visit-check-in", args=[gym.id])
        headers = {"HTTP_AUTHORIZATION": f"Device {token}"}
        assigning = Event()
        second_started = Event()
        continue_assignment = Event()
        original_assign = GymLockerManager.assign

        def pause_before_assignment(manager, gym, user):
            assigning.set()
            if not continue_assignment.wait(timeout=10):
                raise TimeoutError("Check-in did not resume")
            return original_assign(manager, gym, user)

        def check_in(started=None):
            try:
                if started is not None:
                    started.set()
                return APIClient().post(
                    url, {"uid": "CARD1"}, format="json", **headers
                )
            finally:
                connections.close_all()

        with patch.object(GymLockerManager, "assign", pause_before_assignment):
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(check_in)
                try:
                    self.assertTrue(assigning.wait(timeout=10))
                    second = executor.submit(check_in, second_started)
                    self.assertTrue(second_started.wait(timeout=10))
                finally:
                    continue_assignment.set()
                responses = [first.result(timeout=10), second.result(timeout=10)]

        self.assertEqual(sorted(response.status_code for response in responses), [200, 400])
        self.assertEqual(
            next(response for response in responses if response.status_code == 400)
            .data["error_code"],
            GymVisitsError.ALREADY_CHECKED_IN[0],
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.remaining_visits, 1)
        self.assertEqual(GymVisit.objects.filter(user=user).count(), 1)
        self.assertEqual(
            GymLocker.objects.filter(gym=gym, assigned_user=user).count(), 1
        )


class CheckOutConcurrencyTests(TransactionTestCase):
    def test_checkout_locks_user_before_releasing_locker(self):
        gym = Gym.objects.create(name="Gym")
        user = User.objects.create_user(phone_number="09120000001")
        plan = GymMembershipPlan.objects.create_plan(
            name="Plan",
            gym=gym,
            duration_months=1,
            visit_limit=4,
            price=1000,
        )
        order = Order.objects.create(
            buyer=user,
            status=Order.Status.PAID,
            subtotal_amount=1000,
            discount_amount=0,
            tax_amount=0,
            total_amount=1000,
            paid_at=timezone.now(),
        )
        item = OrderItem.objects.create(
            commerce_product=plan.id,
            order=order,
            item_type=CommerceProduct.ProductType.GYM_MEMBERSHIP,
            item_snapshot={},
            quantity=1,
            unit_price=1000,
            subtotal_amount=1000,
            discount_amount=0,
            tax_amount=0,
            total_amount=1000,
        )
        GymSubscription.objects.create(
            subscriber=user,
            plan=plan,
            order_item=item,
            status=GymSubscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
            remaining_visits=2,
            duration_months=1,
        )
        GymLocker.objects.add_lockers(gym=gym, count=1)
        UserNfcCard.objects.assign_card(user=user, uid="CARD1")
        _, token = GymDevice.objects.register_device(
            gym=gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )
        headers = {"HTTP_AUTHORIZATION": f"Device {token}"}
        check_in_url = reverse("gym_visits:gym-visit-check-in", args=[gym.id])
        check_out_url = reverse("gym_visits:gym-visit-check-out", args=[gym.id])
        self.assertEqual(
            APIClient()
            .post(check_in_url, {"uid": "CARD1"}, format="json", **headers)
            .status_code,
            status.HTTP_200_OK,
        )

        releasing = Event()
        continue_checkout = Event()
        original_remove = GymLockerManager.remove_assignment

        def pause_before_release(manager, gym, user):
            releasing.set()
            if not continue_checkout.wait(timeout=10):
                raise TimeoutError("Checkout did not resume")
            return original_remove(manager, gym, user)

        def checkout():
            try:
                return APIClient().post(
                    check_out_url,
                    {"uid": "CARD1"},
                    format="json",
                    **headers,
                )
            finally:
                connections.close_all()

        with patch.object(GymLockerManager, "remove_assignment", pause_before_release):
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(checkout)
                try:
                    self.assertTrue(releasing.wait(timeout=10))
                    with transaction.atomic():
                        with self.assertRaises(DatabaseError):
                            User.objects.select_for_update(nowait=True).get(pk=user.pk)
                finally:
                    continue_checkout.set()
                self.assertEqual(
                    result.result(timeout=10).status_code, status.HTTP_200_OK
                )

        self.assertFalse(
            GymVisit.objects.filter(user=user, checked_out_at__isnull=True).exists()
        )
        self.assertFalse(GymLocker.objects.filter(gym=gym, assigned_user=user).exists())
