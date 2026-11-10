import subprocess
import sys
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from commerce_orders.models import Order
from config.celery import app
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User


SWEEP_TASK_NAME = "gym_subscriptions.tasks.sweep_gym_subscriptions"


class SubscriptionSweepConfigurationTest(SimpleTestCase):
    def test_worker_discovers_scheduled_task_in_fresh_process(self):
        # A direct task import here could hide a broken worker discovery path.
        script = f"""
from celery.app.utils import find_app
app = find_app("config")
app.loader.import_default_modules()
scheduled_name = app.conf.beat_schedule["sweep-gym-subscriptions"]["task"]
assert scheduled_name == {SWEEP_TASK_NAME!r}, scheduled_name
assert scheduled_name in app.tasks, "Scheduled subscription sweep is not registered"
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_beat_schedules_registered_name_daily_at_three(self):
        entries = [
            entry for entry in app.conf.beat_schedule.values()
            if entry["task"] == SWEEP_TASK_NAME
        ]
        self.assertEqual(len(entries), 1)
        schedule = entries[0]["schedule"]
        run_at = datetime(2026, 11, 6, 3, tzinfo=ZoneInfo(settings.CELERY_TIMEZONE))
        previous_run = run_at - timedelta(days=1)

        for now, last_run, expected_due, next_run in (
            (run_at - timedelta(minutes=1), previous_run, False, 60),
            (run_at, previous_run, True, 86400),
            (run_at + timedelta(minutes=1), run_at, False, 86340),
        ):
            with self.subTest(now=now):
                with patch.object(schedule, "now", return_value=now):
                    due = schedule.is_due(last_run)
                self.assertEqual(due.is_due, expected_due)
                self.assertEqual(due.next, next_run)


class SubscriptionSweepTaskTest(TestCase):
    def setUp(self):
        app.loader.import_default_modules()
        self.sweep_task = app.tasks[SWEEP_TASK_NAME]
        self.now = datetime(2026, 11, 6, 12, tzinfo=ZoneInfo("UTC"))
        self.users = [
            User.objects.create_user(phone_number=f"0912000000{number}")
            for number in range(5)
        ]
        gym_a = Gym.objects.create(name="Gym A")
        gym_b = Gym.objects.create(name="Gym B")
        self.plan_a = GymMembershipPlan.objects.create_plan(
            gym=gym_a, name="Plan A", description="Monthly membership",
            duration_months=1, visit_limit=30, price=1000,
        )
        self.plan_b = GymMembershipPlan.objects.create_plan(
            gym=gym_b, name="Plan B", description="Monthly membership",
            duration_months=1, visit_limit=30, price=1000,
        )

    def make_subscription(self, user, *, plan=None, **values):
        plan = plan or self.plan_a
        order = Order.objects.create(
            buyer=user, status=Order.Status.SUCCEEDED,
            subtotal_amount=1000, discount_amount=0, tax_amount=0,
            total_amount=1000, succeeded_at=self.now,
            commerce_product=plan.id,
            product_snapshot={},
        )
        return GymSubscription.objects.create(
            subscriber=user, plan=plan, order=order,
            **{
                "duration_months": plan.duration_months,
                "initial_visits": plan.visit_limit,
                "remaining_visits": plan.visit_limit,
                **values,
            },
        )

    def run_sweep(self):
        # Invoke the actual registered task against Django's isolated test database.
        with patch("gym_subscriptions.tasks.timezone.now", return_value=self.now):
            self.sweep_task()

    def test_registered_sweep_expires_only_stale_active_subscriptions(self):
        expired_by_time = self.make_subscription(
            self.users[0], status="ACTIVE", remaining_visits=10,
            expires_at=self.now - timedelta(microseconds=1),
        )
        expired_by_visits = self.make_subscription(
            self.users[1], plan=self.plan_b, status="ACTIVE", remaining_visits=0,
            expires_at=self.now + timedelta(days=1),
        )
        boundary = self.make_subscription(
            self.users[2], status="ACTIVE", expires_at=self.now,
        )
        healthy = self.make_subscription(
            self.users[3], status="ACTIVE", remaining_visits=1,
            expires_at=self.now + timedelta(microseconds=1),
        )
        pending = self.make_subscription(self.users[4], status="PENDING")
        cancelled = self.make_subscription(
            self.users[0], status="CANCELLED", end_reason="CANCELLED",
            cancelled_at=self.now - timedelta(days=1),
        )
        already_expired = self.make_subscription(
            self.users[1], status="EXPIRED", end_reason="VISITS", remaining_visits=0,
        )
        unchanged = {
            sub.pk: GymSubscription.objects.values().get(pk=sub.pk)
            for sub in (healthy, pending, cancelled, already_expired)
        }

        self.run_sweep()

        for subscription, reason, visits in (
            (expired_by_time, "TIME", 10),
            (expired_by_visits, "VISITS", 0),
            (boundary, "TIME", 30),
        ):
            with self.subTest(subscription=subscription.pk):
                subscription.refresh_from_db()
                self.assertEqual(subscription.status, "EXPIRED")
                self.assertEqual(subscription.end_reason, reason)
                self.assertEqual(subscription.remaining_visits, visits)
        for subscription_id, original in unchanged.items():
            self.assertEqual(
                GymSubscription.objects.values().get(pk=subscription_id), original
            )
        self.assertEqual(GymSubscription.objects.count(), 7)

    def test_sweep_promotes_same_gym_queue_and_is_safe_to_repeat(self):
        expired = self.make_subscription(
            self.users[0], status="ACTIVE", expires_at=self.now - timedelta(days=1),
        )
        first_pending = self.make_subscription(self.users[0], status="PENDING")
        later_pending = self.make_subscription(self.users[0], plan=self.plan_b, status="PENDING")

        self.run_sweep()

        expired.refresh_from_db()
        first_pending.refresh_from_db()
        later_pending.refresh_from_db()
        self.assertEqual(expired.status, "EXPIRED")
        self.assertEqual(expired.end_reason, "TIME")
        self.assertEqual(first_pending.status, "ACTIVE")
        self.assertEqual(first_pending.remaining_visits, 30)
        self.assertEqual(first_pending.started_at, self.now)
        self.assertEqual(
            first_pending.expires_at,
            datetime(2026, 12, 6, 12, tzinfo=ZoneInfo("UTC")),
        )
        self.assertEqual(later_pending.status, "PENDING")
        self.assertIsNone(later_pending.started_at)
        original = list(GymSubscription.objects.order_by("pk").values())

        self.run_sweep()

        self.assertEqual(list(GymSubscription.objects.order_by("pk").values()), original)

    def test_sweep_does_not_change_other_gym_active_subscription(self):
        stale = self.make_subscription(
            self.users[0], status="ACTIVE", expires_at=self.now - timedelta(days=1),
        )
        other = self.make_subscription(
            self.users[0], plan=self.plan_b, status="ACTIVE",
            expires_at=self.now + timedelta(days=5),
        )

        self.run_sweep()

        stale.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(stale.status, "EXPIRED")
        self.assertEqual(other.status, "ACTIVE")

    def test_sweep_without_subscriptions_succeeds(self):
        self.run_sweep()
        self.assertFalse(GymSubscription.objects.exists())

    def test_sweep_refreshes_expired_and_promoted_subscription_caches(self):
        active = self.make_subscription(
            self.users[0], status="ACTIVE", remaining_visits=10,
            expires_at=self.now - timedelta(days=1),
        )
        pending = self.make_subscription(self.users[0], status="PENDING")
        client = APIClient()
        client.force_authenticate(user=self.users[0])
        list_url = reverse("gym_subscriptions:gym-subscription-list")

        def read_states():
            response = client.get(list_url)
            self.assertEqual(response.status_code, 200)
            list_states = {
                item["id"]: item["status"]
                for item in response.data["subscriptions"]
            }
            detail_states = {}
            for subscription in (active, pending):
                detail_url = reverse(
                    "gym_subscriptions:gym-subscription-detail",
                    kwargs={"subscription_id": subscription.pk},
                )
                detail = client.get(detail_url)
                self.assertEqual(detail.status_code, 200)
                detail_states[str(subscription.pk)] = detail.data["subscription"]["status"]
            return list_states, detail_states

        expected_before = {str(active.pk): "ACTIVE", str(pending.pk): "PENDING"}
        self.assertEqual(read_states(), (expected_before, expected_before))

        with self.captureOnCommitCallbacks(execute=True):
            self.run_sweep()

        active.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(active.status, "EXPIRED")
        self.assertEqual(pending.status, "ACTIVE")
        expected_after = {str(active.pk): "EXPIRED", str(pending.pk): "ACTIVE"}
        self.assertEqual(read_states(), (expected_after, expected_after))
