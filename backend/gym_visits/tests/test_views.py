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
from commerce_orders.models import Order
from core.errors import (
    APIError,
    GymDeviceError,
    GymVisitsError,
    GymSubscriptionError,
    UserNfcCardError,
    UserAccountError,
    UserValidationError,
    GymLockerError,
)
from core.cache import USER_SUBSCRIPTION, cache_key
from gym.models import Gym
from gym_auth.models import UserGymRole
from gym_devices.models import GymDevice
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from gym_visits.models import GymVisit, GymVisitManager
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

    def _make_order(self, user, plan):
        order = Order.objects.create(
            buyer=user,
            status=Order.Status.SUCCEEDED,
            subtotal_amount=0,
            discount_amount=0,
            tax_amount=0,
            total_amount=0,
            succeeded_at=timezone.now(),
            commerce_product=plan.id,
            product_snapshot={},
        )

        return order

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
            order=self._make_order(user, plan),
            status=GymSubscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=expires_in_days),
            remaining_visits=remaining,
            duration_months=plan.duration_months,
        )

    def create_subscription(self, user, plan):
        return GymSubscription.objects.create_subscription(
            subscriber=user,
            order=self._make_order(user, plan),
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
    def test_inactive_pending_user_keeps_request_and_receives_no_card(self):
        self.make_active_subscription(self.user, self.plan_a)
        self.create_pending_card_assignment(self.gym_a, self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.check_in(gym=self.gym_a, token=self.token_a, uid="NEW_CARD")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], UserAccountError.USER_ACCOUNT_INACTIVE[0])
        self.assertEqual(cache.get(f"nfc_card_assign_{self.gym_a.pk}"), self.user.pk)
        self.assertFalse(UserNfcCard.objects.filter(user=self.user).exists())
        self.assertFalse(GymVisit.objects.filter(user=self.user).exists())

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
        self.assertEqual(GymSubscription.objects.get(subscriber=self.user).remaining_visits, 9)

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
        self.assertFalse(GymLocker.objects.filter(gym=self.gym_a, assigned_user=self.user).exists())


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
        self.assertEqual(response.data["error_code"], GymVisitsError.ALREADY_CHECKED_IN[0])
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
            self.assertEqual(response.json()["data"]["subscription"]["status"], expected_status)
        response = client.get(reverse("gym_subscriptions:gym-subscription-list"))
        self.assertEqual(response.status_code, 200)
        states = {
            subscription["id"]: subscription["status"] for subscription in response.json()["data"]["subscriptions"]
        }
        for subscription, expected_status in expected:
            self.assertEqual(states[str(subscription.pk)], expected_status)

    def test_last_visit_promotes_same_gym_and_preserves_other_gym_queue(self):
        active = self.make_active_subscription(self.user, self.plan_a, remaining=1)
        pending_b = self.make_pending_subscription(self.user, self.make_plan_b())
        later_a = self.make_pending_subscription(self.user, self.plan_a)
        self.assert_subscription_api_states((active, "ACTIVE"), (pending_b, "PENDING"), (later_a, "PENDING"))
        keys = {sub.pk: cache_key(USER_SUBSCRIPTION, self.user.pk, sub.pk) for sub in (active, pending_b)}

        with self.captureOnCommitCallbacks(execute=True):
            response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
            self.assertEqual(response.status_code, 200)
            for sub_id, key in keys.items():
                self.assertEqual(cache_key(USER_SUBSCRIPTION, self.user.pk, sub_id), key)

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
        self.assert_subscription_api_states((active, "EXPIRED"), (pending_b, "PENDING"), (later_a, "ACTIVE"))

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
            GymVisit.objects.get(user=self.user, checked_out_at__isnull=True).subscription_id,
            pending_b.pk,
        )

    def test_check_in_recovers_pending_subscription_after_previous_expired(self):
        expired = self.make_active_subscription(self.user, self.plan_a, remaining=0)
        pending_b = self.make_pending_subscription(self.user, self.make_plan_b())
        expired.expire(reason=GymSubscription.EndReason.VISITS)
        self.assert_subscription_api_states((expired, "EXPIRED"), (pending_b, "PENDING"))

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
        self.assertEqual(retry.json()["error_code"], GymVisitsError.ALREADY_CHECKED_IN[0])
        self.assertEqual(callbacks, [])
        pending_b.refresh_from_db()
        self.assertEqual(pending_b.remaining_visits, 29)
        self.assertEqual(GymVisit.objects.filter(user=self.user).count(), 1)

    def test_check_in_at_other_gym_does_not_expire_first_gym_subscription(self):
        expired = self.make_active_subscription(self.user, self.plan_a, remaining=5, expires_in_days=-1)
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
        self.assertEqual(response.json()["error_code"], GymLockerError.NO_AVAILABLE_LOCKER[0])
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
        self.assertEqual(response.json()["error_code"], GymLockerError.NO_AVAILABLE_LOCKER[0])
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
        self.assertEqual(GymVisit.objects.get(user=self.user).subscription_id, pending_b.pk)

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
        self.assertFalse(GymVisit.objects.filter(user=self.user).exists())
        self.assertFalse(GymLocker.objects.filter(assigned_user=self.user).exists())
        self.assertEqual(
            GymSubscription.objects.get(subscriber=self.user).remaining_visits,
            10,
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

    def test_inactive_user_can_open_locker_and_check_out(self):
        _, locker_token = GymDevice.objects.register_device(
            gym=self.gym_a,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )
        locker_url = reverse("gym_locks:gym_locks-open-nfc", args=[self.gym_a.pk])
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        locker_response = self.client.post(
            locker_url, {"uid": "CARD1"}, format="json", **self.auth_header(locker_token)
        )
        self.assertEqual(locker_response.status_code, 200)
        self.assertEqual(
            locker_response.data["locker_number"],
            GymLocker.objects.get(gym=self.gym_a, assigned_user=self.user).number,
        )
        self.assertEqual(self.check_out(gym=self.gym_a, token=self.token_a, uid="CARD1").status_code, 200)
        visit = GymVisit.objects.get(user=self.user)
        self.assertIsNotNone(visit.checked_out_at)
        self.assertFalse(GymLocker.objects.filter(assigned_user=self.user).exists())
        after = self.client.post(locker_url, {"uid": "CARD1"}, format="json", **self.auth_header(locker_token))
        self.assertEqual(after.status_code, 404)
        self.assertEqual(after.data["error_code"], GymLockerError.USER_NOT_ASSIGNED[0])

    def test_locker_open_stays_scoped_to_device_gym_and_card(self):
        _, locker_token_a = GymDevice.objects.register_device(
            gym=self.gym_a, device_type=GymDevice.GymDeviceType.LOCKER
        )
        _, locker_token_b = GymDevice.objects.register_device(
            gym=self.gym_b, device_type=GymDevice.GymDeviceType.LOCKER
        )
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        url_a = reverse("gym_locks:gym_locks-open-nfc", args=[self.gym_a.pk])
        url_b = reverse("gym_locks:gym_locks-open-nfc", args=[self.gym_b.pk])
        cases = (
            (url_a, locker_token_b, "CARD1"),
            (url_b, locker_token_b, "CARD1"),
            (url_a, locker_token_a, "WRONG_CARD"),
            (url_a, self.token_a, "CARD1"),
        )
        for url, token, uid in cases:
            with self.subTest(url=url, uid=uid):
                response = self.client.post(url, {"uid": uid}, format="json", **self.auth_header(token))
                self.assertEqual(response.status_code, 404)
        self.assertTrue(GymVisit.objects.filter(user=self.user, checked_out_at__isnull=True).exists())

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
        plan = GymMembershipPlan.objects.create_plan(name="Plan", gym=gym, duration_months=1, visit_limit=4, price=1000)
        order = Order.objects.create(
            buyer=user,
            status=Order.Status.SUCCEEDED,
            subtotal_amount=1000,
            discount_amount=0,
            tax_amount=0,
            total_amount=1000,
            succeeded_at=timezone.now(),
            commerce_product=plan.id,
            product_snapshot={},
        )
        subscription = GymSubscription.objects.create(
            subscriber=user,
            plan=plan,
            order=order,
            status=GymSubscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=30),
            remaining_visits=2,
            duration_months=1,
        )
        GymLocker.objects.add_lockers(gym=gym, count=2)
        UserNfcCard.objects.assign_card(user=user, uid="CARD1")
        _, token = GymDevice.objects.register_device(gym=gym, device_type=GymDevice.GymDeviceType.ENTRANCE)
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
                return APIClient().post(url, {"uid": "CARD1"}, format="json", **headers)
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
            next(response for response in responses if response.status_code == 400).data["error_code"],
            GymVisitsError.ALREADY_CHECKED_IN[0],
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.remaining_visits, 1)
        self.assertEqual(GymVisit.objects.filter(user=user).count(), 1)
        self.assertEqual(GymLocker.objects.filter(gym=gym, assigned_user=user).count(), 1)


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
            status=Order.Status.SUCCEEDED,
            subtotal_amount=1000,
            discount_amount=0,
            tax_amount=0,
            total_amount=1000,
            succeeded_at=timezone.now(),
            commerce_product=plan.id,
            product_snapshot={},
        )
        GymSubscription.objects.create(
            subscriber=user,
            plan=plan,
            order=order,
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
            APIClient().post(check_in_url, {"uid": "CARD1"}, format="json", **headers).status_code,
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
                self.assertEqual(result.result(timeout=10).status_code, status.HTTP_200_OK)

        self.assertFalse(GymVisit.objects.filter(user=user, checked_out_at__isnull=True).exists())
        self.assertFalse(GymLocker.objects.filter(gym=gym, assigned_user=user).exists())


class ManualAttendanceTests(NfcFlowTestBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(phone_number="09120000030", password="x")
        self.owner = User.objects.create_user(phone_number="09120000031")
        self.staff = User.objects.create_user(phone_number="09120000032")
        self.coach = User.objects.create_user(phone_number="09120000033")
        UserGymRole.objects.create_owner(self.owner, self.gym_a)
        UserGymRole.objects.create_staff(self.staff, self.gym_a)
        UserGymRole.objects.create_coach(self.coach, self.gym_a)
        self.plan_b = GymMembershipPlan.objects.create_plan(
            name="Plan B",
            gym=self.gym_b,
            duration_months=1,
            visit_limit=30,
            price=1000,
        )

    def manual(self, action, actor, gym=None):
        gym = gym or self.gym_a
        self.client.force_authenticate(user=actor)
        return self.client.post(
            reverse(f"gym_visits:gym-visit-manual-{action}", args=[gym.pk]),
            {"phone_number": self.user.phone_number},
            format="json",
        )

    def test_manual_check_in_validates_and_normalizes_phone(self):
        subscription = self.make_active_subscription(self.user, self.plan_a)
        self.client.force_authenticate(user=self.staff)
        url = reverse("gym_visits:gym-visit-manual-check-in", args=[self.gym_a.pk])
        for data in ({}, {"phone_number": "invalid"}, {"phone_number": 123}):
            with self.subTest(data=data):
                response = self.client.post(url, data, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.data["error_code"],
                    UserValidationError.INVALID_PHONE_NUMBER[0],
                )
                self.assertFalse(GymVisit.objects.filter(user=self.user).exists())
                self.assertFalse(GymLocker.objects.filter(assigned_user=self.user).exists())
                subscription.refresh_from_db()
                self.assertEqual(subscription.remaining_visits, 10)
        response = self.client.post(url, {"phone_number": f"  {self.user.phone_number}  "}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GymVisit.objects.filter(user=self.user).count(), 1)

    def test_manual_check_out_validates_phone_for_inactive_user(self):
        self.make_active_subscription(self.user, self.plan_a)
        self.assertEqual(self.manual("check-in", self.staff).status_code, 200)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.client.force_authenticate(user=self.staff)
        url = reverse("gym_visits:gym-visit-manual-check-out", args=[self.gym_a.pk])
        for data in ({}, {"phone_number": "invalid"}, {"phone_number": 123}):
            with self.subTest(data=data):
                response = self.client.post(url, data, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.data["error_code"],
                    UserValidationError.INVALID_PHONE_NUMBER[0],
                )
                self.assertTrue(GymVisit.objects.filter(user=self.user, checked_out_at__isnull=True).exists())
                self.assertTrue(GymLocker.objects.filter(assigned_user=self.user).exists())
        response = self.client.post(url, {"phone_number": f"  {self.user.phone_number}  "}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(GymVisit.objects.filter(user=self.user, checked_out_at__isnull=True).exists())
        self.assertFalse(GymLocker.objects.filter(assigned_user=self.user).exists())

    def test_manual_locker_open_validates_phone_for_inactive_user(self):
        self.make_active_subscription(self.user, self.plan_a)
        self.assertEqual(self.manual("check-in", self.staff).status_code, 200)
        locker = GymLocker.objects.get(gym=self.gym_a, assigned_user=self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.client.force_authenticate(user=self.staff)
        url = reverse("gym_locks:gym_locks-open-manual", args=[self.gym_a.pk])
        for data in ({}, {"phone_number": "invalid"}, {"phone_number": 123}):
            with self.subTest(data=data):
                response = self.client.post(url, data, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.data["error_code"],
                    UserValidationError.INVALID_PHONE_NUMBER[0],
                )
                self.assertTrue(GymVisit.objects.filter(user=self.user, checked_out_at__isnull=True).exists())
                locker.refresh_from_db()
                self.assertEqual(locker.assigned_user_id, self.user.pk)
        response = self.client.post(url, {"phone_number": f"  {self.user.phone_number}  "}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["locker_number"], locker.number)

    def test_admin_can_manage_attendance_at_any_gym(self):
        self.make_active_subscription(self.user, self.plan_b)
        self.assertEqual(self.manual("check-in", self.admin, self.gym_b).status_code, 200)
        visit = GymVisit.objects.get(user=self.user, gym=self.gym_b)
        self.assertEqual(visit.checked_in_method, GymVisit.Method.STAFF)
        self.assertEqual(self.manual("check-out", self.admin, self.gym_b).status_code, 200)
        visit.refresh_from_db()
        self.assertEqual(visit.checked_out_method, GymVisit.Method.STAFF)

    def test_owner_and_staff_can_manage_own_gym(self):
        subscription = self.make_active_subscription(self.user, self.plan_a)
        for actor in (self.owner, self.staff):
            with self.subTest(actor=actor.pk):
                self.assertEqual(self.manual("check-in", actor).status_code, 200)
                self.assertEqual(self.manual("check-out", actor).status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.remaining_visits, 8)
        self.assertEqual(GymVisit.objects.filter(user=self.user).count(), 2)

    def test_owner_staff_coach_and_regular_user_permissions(self):
        self.make_active_subscription(self.user, self.plan_b)
        for actor, gym in (
            (self.owner, self.gym_b),
            (self.staff, self.gym_b),
            (self.coach, self.gym_a),
            (self.other_user, self.gym_a),
        ):
            for action in ("check-in", "check-out"):
                with self.subTest(actor=actor.pk, action=action):
                    self.assertEqual(self.manual(action, actor, gym).status_code, 404)
        self.assertFalse(GymVisit.objects.filter(user=self.user).exists())

    def test_check_in_consumes_one_visit_and_checkout_releases_locker(self):
        subscription = self.make_active_subscription(self.user, self.plan_a)
        self.assertEqual(self.manual("check-in", self.staff).status_code, 200)
        visit = GymVisit.objects.get(user=self.user)
        self.assertEqual(visit.checked_in_method, GymVisit.Method.STAFF)
        subscription.refresh_from_db()
        self.assertEqual(subscription.remaining_visits, 9)
        self.assertTrue(GymLocker.objects.filter(gym=self.gym_a, assigned_user=self.user).exists())
        self.assertEqual(self.manual("check-out", self.staff).status_code, 200)
        visit.refresh_from_db()
        subscription.refresh_from_db()
        self.assertIsNotNone(visit.checked_out_at)
        self.assertEqual(visit.checked_out_method, GymVisit.Method.STAFF)
        self.assertEqual(subscription.remaining_visits, 9)
        self.assertFalse(GymLocker.objects.filter(gym=self.gym_a, assigned_user=self.user).exists())

    def test_open_visit_blocks_second_check_in_even_at_other_gym(self):
        first = self.make_active_subscription(self.user, self.plan_a)
        second = self.make_active_subscription(self.user, self.plan_b)
        self.assertEqual(self.manual("check-in", self.admin).status_code, 200)
        response = self.manual("check-in", self.admin, self.gym_b)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], GymVisitsError.ALREADY_CHECKED_IN[0])
        self.assertEqual(GymVisit.objects.filter(user=self.user).count(), 1)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.remaining_visits, second.remaining_visits), (9, 10))

    def test_pending_renewal_promotes_only_at_same_gym(self):
        active = self.make_active_subscription(self.user, self.plan_a, remaining=2)
        pending = self.make_pending_subscription(self.user, self.plan_a)
        active.expires_at = timezone.now() - timedelta(seconds=1)
        active.save(update_fields=["expires_at"])
        self.assertEqual(self.manual("check-in", self.staff).status_code, 200)
        active.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(active.status, GymSubscription.Status.EXPIRED)
        self.assertEqual(pending.status, GymSubscription.Status.ACTIVE)
        self.assertEqual(pending.remaining_visits, 29)
        self.assertEqual(GymVisit.objects.get(user=self.user).subscription_id, pending.pk)

    def test_pending_subscription_at_other_gym_cannot_check_in(self):
        self.make_pending_subscription(self.user, self.plan_b)
        response = self.manual("check-in", self.staff)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0])
        self.assertFalse(GymVisit.objects.filter(user=self.user).exists())
        self.assertFalse(GymLocker.objects.filter(assigned_user=self.user).exists())

    def test_check_in_rolls_back_when_locker_assignment_fails(self):
        subscription = self.make_active_subscription(self.user, self.plan_a)
        GymLocker.objects.filter(gym=self.gym_a).delete()
        response = self.manual("check-in", self.staff)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], GymLockerError.NO_AVAILABLE_LOCKER[0])
        subscription.refresh_from_db()
        self.assertEqual(subscription.remaining_visits, 10)
        self.assertFalse(GymVisit.objects.filter(user=self.user).exists())

    def test_check_in_rolls_back_when_visit_creation_fails(self):
        subscription = self.make_active_subscription(self.user, self.plan_a)
        with patch.object(GymVisitManager, "check_in", side_effect=DatabaseError("visit write failed")):
            with self.assertRaises(DatabaseError):
                self.manual("check-in", self.staff)
        subscription.refresh_from_db()
        self.assertEqual(subscription.remaining_visits, 10)
        self.assertFalse(GymVisit.objects.filter(user=self.user).exists())
        self.assertFalse(GymLocker.objects.filter(assigned_user=self.user).exists())

    def test_inactive_target_cannot_check_in(self):
        subscription = self.make_active_subscription(self.user, self.plan_a)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.manual("check-in", self.staff)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], UserAccountError.USER_ACCOUNT_INACTIVE[0])
        subscription.refresh_from_db()
        self.assertEqual(subscription.remaining_visits, 10)
        self.assertFalse(GymVisit.objects.filter(user=self.user).exists())
        self.assertFalse(GymLocker.objects.filter(assigned_user=self.user).exists())

    def test_inactive_target_cannot_create_second_visit(self):
        subscription = self.make_active_subscription(self.user, self.plan_a)
        self.assign_card(self.user, "CARD1")
        self.assertEqual(self.manual("check-in", self.staff).status_code, 200)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        manual_response = self.manual("check-in", self.staff)
        self.client.force_authenticate(user=None)
        nfc_response = self.check_in(gym=self.gym_a, token=self.token_a, uid="CARD1")
        for response in (manual_response, nfc_response):
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["error_code"], UserAccountError.USER_ACCOUNT_INACTIVE[0])
        subscription.refresh_from_db()
        self.assertEqual(subscription.remaining_visits, 9)
        self.assertEqual(GymVisit.objects.filter(user=self.user).count(), 1)

    def test_inactive_target_can_check_out_after_subscription_expires(self):
        subscription = self.make_active_subscription(self.user, self.plan_a)
        self.assertEqual(self.manual("check-in", self.staff).status_code, 200)
        subscription.expire(GymSubscription.EndReason.TIME)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.manual("check-out", self.staff).status_code, 200)
        visit = GymVisit.objects.get(user=self.user)
        subscription.refresh_from_db()
        self.assertIsNotNone(visit.checked_out_at)
        self.assertEqual(subscription.remaining_visits, 9)
        self.assertFalse(GymLocker.objects.filter(assigned_user=self.user).exists())

    def test_inactive_target_can_use_manual_locker_until_checkout(self):
        self.make_active_subscription(self.user, self.plan_a)
        self.assertEqual(self.manual("check-in", self.staff).status_code, 200)
        locker = GymLocker.objects.get(gym=self.gym_a, assigned_user=self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        open_url = reverse("gym_locks:gym_locks-open-manual", args=[self.gym_a.pk])
        self.client.force_authenticate(user=self.staff)
        data = {"phone_number": self.user.phone_number}
        response = self.client.post(open_url, data, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["locker_number"], locker.number)
        wrong_gym_url = reverse("gym_locks:gym_locks-open-manual", args=[self.gym_b.pk])
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.post(wrong_gym_url, data, format="json").status_code, 404)
        self.assertEqual(self.manual("check-out", self.staff).status_code, 200)
        self.client.force_authenticate(user=self.staff)
        after = self.client.post(open_url, data, format="json")
        self.assertEqual(after.status_code, 404)
        self.assertEqual(after.data["error_code"], GymLockerError.USER_NOT_ASSIGNED[0])

    def test_checkout_requires_matching_open_visit(self):
        self.make_active_subscription(self.user, self.plan_a)
        self.assertEqual(self.manual("check-in", self.admin).status_code, 200)
        response = self.manual("check-out", self.admin, self.gym_b)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error_code"], GymVisitsError.VISIT_NOT_FOUND[0])
        self.assertTrue(GymVisit.objects.filter(user=self.user, checked_out_at__isnull=True).exists())
        self.assertEqual(self.manual("check-out", self.admin).status_code, 200)
        self.assertEqual(self.manual("check-out", self.admin).status_code, 404)
