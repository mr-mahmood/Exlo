from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import subprocess
import sys
from threading import Barrier
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection, connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from commerce_orders.models import Order
from commerce_orders.tasks import process_seller_settlements
from commerce_payments.models import Payment
from commerce_refunds.models import Refund
from commerce_refunds.tasks import process_pending_refunds
from commerce_wallet.models import Wallet
from commerce_wallet_ledger.models import WalletLedger
from config.celery import app
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User


class CommerceTaskConfigurationTests(SimpleTestCase):
    def test_worker_discovers_both_scheduled_commerce_tasks_in_fresh_process(self):
        script = """
from celery.app.utils import find_app
app = find_app("config")
app.loader.import_default_modules()
for task in ("commerce_refunds.tasks.process_pending_refunds", "commerce_orders.tasks.process_seller_settlements"):
    assert task in app.tasks, f"Task not registered: {task}"
"""
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=settings.BASE_DIR, capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_refunds_run_at_0320_and_settlements_at_0330_daily(self):
        for task_name, minute in (
            ("commerce_refunds.tasks.process_pending_refunds", 20),
            ("commerce_orders.tasks.process_seller_settlements", 30),
        ):
            with self.subTest(task=task_name):
                entries = [entry for entry in app.conf.beat_schedule.values() if entry["task"] == task_name]
                self.assertEqual(len(entries), 1)
                schedule = entries[0]["schedule"]
                run_at = datetime(2026, 11, 12, 3, minute, tzinfo=ZoneInfo(settings.CELERY_TIMEZONE))
                for now, last_run, expected_due, next_run in (
                    (run_at - timedelta(minutes=1), run_at - timedelta(days=1), False, 60),
                    (run_at, run_at - timedelta(days=1), True, 86400),
                    (run_at + timedelta(minutes=1), run_at, False, 86340),
                ):
                    with self.subTest(now=now), patch.object(schedule, "now", return_value=now):
                        due = schedule.is_due(last_run)
                        self.assertEqual(due.is_due, expected_due)
                        self.assertEqual(due.next, next_run)


class SellerSettlementTaskTests(TestCase):
    def make_order(self, **values):
        return Order.objects.create(
            **{
                "commerce_product": self.plan.id,
                "buyer": self.buyer,
                "seller": self.seller,
                "subtotal_amount": 1200,
                "discount_amount": 200,
                "tax_amount": 50,
                "product_snapshot": {"name": "Monthly membership", "visit_limit": 30},
                "status": Order.Status.SUCCEEDED,
                "succeeded_at": self.now,
                **values,
            }
        )

    def make_subscription(self, order, **values):
        subscription = GymSubscription.objects.create(
            **{
                "order": order,
                "subscriber": order.buyer,
                "plan": self.plan,
                "status": GymSubscription.Status.EXPIRED,
                "initial_visits": 30,
                "remaining_visits": 30,
                "duration_months": 1,
                "started_at": self.now - timedelta(days=31),
                "expires_at": self.now - timedelta(days=1),
                **values,
            }
        )
        GymSubscription.objects.filter(pk=subscription.pk).update(created_at=self.now - timedelta(days=31))
        subscription.refresh_from_db()
        return subscription

    def make_order_payment(self, order, **values):
        return Payment.objects.create(
            **{
                "order": order,
                "purpose": Payment.Purpose.ORDER_PAYMENT,
                "payment_method": Payment.Method.ONLINE_GATEWAY,
                "amount": 1050,
                "gateway_fee_amount": 250000,
                "status": Payment.Status.PAID,
                "paid_at": self.now,
                **values,
            }
        )

    def setUp(self):
        super().setUp()
        self.now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        self.buyer = User.objects.create_user(phone_number="09120000001")
        self.seller = User.objects.create_user(phone_number="09120000002")
        self.other_user = User.objects.create_user(phone_number="09120000003")
        self.buyer_wallet = Wallet.objects.create(owner=self.buyer, balance=5000)
        self.seller_wallet = Wallet.objects.create(owner=self.seller, balance=700)
        self.other_wallet = Wallet.objects.create(owner=self.other_user, balance=900)
        self.gym = Gym.objects.create(name="Commerce test gym")
        self.plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Monthly membership",
            description="Commerce test membership",
            duration_months=1,
            visit_limit=30,
            price=1200,
        )
        self.order = self.make_order()
        self.subscription = self.make_subscription(self.order)
        self.payment = self.make_order_payment(self.order)

    def run_task(self):
        with patch("gym_subscriptions.models.timezone.now", return_value=self.now):
            process_seller_settlements()

    def assert_unsettled(self):
        self.order.refresh_from_db()
        self.seller_wallet.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.other_wallet.refresh_from_db()
        self.assertEqual(self.order.settlement_status, "HELD")
        self.assertEqual(self.seller_wallet.balance, 700)
        self.assertEqual(self.buyer_wallet.balance, 5000)
        self.assertEqual(self.other_wallet.balance, 900)
        self.assertFalse(WalletLedger.objects.exists())

    def test_gateway_sale_credits_seller_net_of_discount_without_tax_or_gateway_fee(self):
        self.run_task()

        self.order.refresh_from_db()
        self.seller_wallet.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.other_wallet.refresh_from_db()
        self.payment.refresh_from_db()
        self.subscription.refresh_from_db()
        self.assertEqual(self.order.settlement_status, "RELEASED")
        self.assertEqual(self.order.status, "SUCCEEDED")
        self.assertEqual(self.seller_wallet.balance, 1700)
        self.assertEqual(self.buyer_wallet.balance, 5000)
        self.assertEqual(self.other_wallet.balance, 900)
        self.assertEqual(self.payment.status, "PAID")
        self.assertEqual(self.subscription.status, "EXPIRED")
        entry = WalletLedger.objects.get()
        self.assertEqual(
            (entry.wallet_id, entry.payment_id, entry.entry_type, entry.reason, entry.amount, entry.balance_before),
            (self.seller_wallet.pk, self.payment.pk, "CREDIT", "SALE_REVENUE", 1000, 700),
        )

    def test_wallet_sale_releases_same_seller_revenue(self):
        Payment.objects.filter(pk=self.payment.pk).update(
            payment_method="WALLET", wallet=self.buyer_wallet, gateway_fee_amount=0
        )
        self.run_task()

        self.seller_wallet.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.seller_wallet.balance, 1700)
        self.assertEqual(self.order.settlement_status, "RELEASED")
        self.assertEqual(WalletLedger.objects.get().amount, 1000)

    def test_repeated_execution_preserves_balance_ledger_and_timestamps(self):
        self.run_task()
        before_wallets = list(Wallet.objects.order_by("pk").values())
        before_orders = list(Order.objects.order_by("pk").values())
        before_entries = list(WalletLedger.objects.values())
        self.run_task()

        self.assertEqual(list(Wallet.objects.order_by("pk").values()), before_wallets)
        self.assertEqual(list(Order.objects.order_by("pk").values()), before_orders)
        self.assertEqual(list(WalletLedger.objects.values()), before_entries)

    def test_unsuccessful_orders_are_not_settled(self):
        for status in ("PENDING", "FAILED"):
            with self.subTest(status=status):
                Order.objects.filter(pk=self.order.pk).update(status=status)
                self.run_task()
                self.assert_unsettled()

    def test_released_or_voided_settlements_are_not_credited(self):
        for settlement in ("RELEASED", "VOIDED"):
            with self.subTest(settlement=settlement):
                Order.objects.filter(pk=self.order.pk).update(settlement_status=settlement)
                self.run_task()
                self.seller_wallet.refresh_from_db()
                self.order.refresh_from_db()
                self.assertEqual(self.seller_wallet.balance, 700)
                self.assertEqual(self.order.settlement_status, settlement)
                self.assertFalse(WalletLedger.objects.exists())

    def test_pending_failed_or_wrong_amount_payment_does_not_release_revenue(self):
        for status, amount in (("PENDING", 1050), ("FAILED", 1050), ("PAID", 1049), ("PAID", 1051)):
            with self.subTest(status=status, amount=amount):
                Payment.objects.filter(pk=self.payment.pk).update(
                    status=status, amount=amount, paid_at=self.now if status == "PAID" else None
                )
                self.run_task()
                self.assert_unsettled()

    def test_missing_payment_does_not_release_revenue(self):
        self.payment.delete()
        self.run_task()
        self.assert_unsettled()

    def test_membership_refund_window_delays_settlement_until_exactly_48_hours(self):
        GymSubscription.objects.filter(pk=self.subscription.pk).update(
            status="ACTIVE",
            created_at=self.now - timedelta(hours=48) + timedelta(microseconds=1),
            started_at=self.now - timedelta(days=1),
            expires_at=self.now + timedelta(days=29),
        )
        self.run_task()
        self.assert_unsettled()

        self.now += timedelta(microseconds=1)
        self.run_task()
        self.order.refresh_from_db()
        self.seller_wallet.refresh_from_db()
        self.assertEqual(self.order.settlement_status, "RELEASED")
        self.assertEqual(self.seller_wallet.balance, 1700)

    def test_used_membership_can_settle_before_refund_window_ends(self):
        GymSubscription.objects.filter(pk=self.subscription.pk).update(
            status="ACTIVE",
            remaining_visits=29,
            created_at=self.now - timedelta(hours=1),
            started_at=self.now - timedelta(hours=1),
            expires_at=self.now + timedelta(days=30),
        )
        self.run_task()
        self.order.refresh_from_db()
        self.assertEqual(self.order.settlement_status, "RELEASED")
        self.assertEqual(WalletLedger.objects.get().amount, 1000)

    def test_pending_and_completed_refunds_both_block_settlement(self):
        refund = Refund.objects.create(payment=self.payment, amount=1050)
        for status in ("PENDING", "COMPLETED"):
            with self.subTest(status=status):
                Refund.objects.filter(pk=refund.pk).update(status=status)
                self.run_task()
                self.assert_unsettled()

    def test_refund_on_another_payment_attempt_also_blocks_settlement(self):
        old_attempt = self.make_order_payment(self.order, status="FAILED", paid_at=None)
        Refund.objects.create(payment=old_attempt, amount=1050)
        self.run_task()
        self.assert_unsettled()

    def test_revenue_ledger_for_another_payment_attempt_prevents_duplicate_credit(self):
        old_attempt = self.make_order_payment(self.order, status="FAILED", paid_at=None)
        WalletLedger.objects.create_seller_revenue_ledger(
            wallet=self.seller_wallet, payment=old_attempt, amount=1000, balance_before=700
        )
        self.seller_wallet.credit(1000)
        self.run_task()

        self.seller_wallet.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.seller_wallet.balance, 1700)
        self.assertEqual(self.order.settlement_status, "HELD")
        self.assertEqual(WalletLedger.objects.count(), 1)

    def test_missing_seller_wallet_leaves_order_held(self):
        self.seller_wallet.delete()
        self.run_task()
        self.order.refresh_from_db()
        self.assertEqual(self.order.settlement_status, "HELD")
        self.assertFalse(WalletLedger.objects.exists())
        self.assertFalse(Wallet.objects.filter(owner=self.seller).exists())

    def test_missing_membership_leaves_order_held(self):
        self.subscription.delete()
        self.run_task()
        self.assert_unsettled()

    def test_ledger_failure_rolls_back_wallet_credit(self):
        with patch.object(
            WalletLedger.objects, "create_seller_revenue_ledger", side_effect=RuntimeError("insert failed")
        ) as failure:
            self.run_task()
        failure.assert_called_once()
        self.assert_unsettled()

    def test_settlement_failure_rolls_back_wallet_credit_and_inserted_ledger(self):
        with patch.object(Order, "mark_settlement_released", side_effect=RuntimeError("update failed")) as failure:
            self.run_task()
        failure.assert_called_once()
        self.assert_unsettled()

    def test_failed_item_does_not_block_valid_sale_and_can_be_retried(self):
        bad_order = self.make_order()
        self.make_subscription(bad_order)
        bad_payment = self.make_order_payment(bad_order)
        create_ledger = WalletLedger.objects.create_seller_revenue_ledger

        def fail_one_payment(**values):
            if values["payment"].pk == bad_payment.pk:
                raise RuntimeError("one ledger insert failed")
            return create_ledger(**values)

        with patch.object(WalletLedger.objects, "create_seller_revenue_ledger", side_effect=fail_one_payment):
            self.run_task()
        self.seller_wallet.refresh_from_db()
        self.order.refresh_from_db()
        bad_order.refresh_from_db()
        self.assertEqual(self.seller_wallet.balance, 1700)
        self.assertEqual(self.order.settlement_status, "RELEASED")
        self.assertEqual(bad_order.settlement_status, "HELD")
        self.assertEqual(WalletLedger.objects.get().payment_id, self.payment.pk)

        self.run_task()
        self.seller_wallet.refresh_from_db()
        bad_order.refresh_from_db()
        self.assertEqual(self.seller_wallet.balance, 2700)
        self.assertEqual(bad_order.settlement_status, "RELEASED")
        self.assertEqual(WalletLedger.objects.count(), 2)

    def test_empty_candidate_batch_changes_no_wallets(self):
        Order.objects.filter(pk=self.order.pk).update(status="PENDING")
        self.run_task()
        self.assert_unsettled()


class SellerSettlementConcurrencyTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        self.buyer = User.objects.create_user(phone_number="09120000001")
        self.seller = User.objects.create_user(phone_number="09120000002")
        self.other_user = User.objects.create_user(phone_number="09120000003")
        self.buyer_wallet = Wallet.objects.create(owner=self.buyer, balance=5000)
        self.seller_wallet = Wallet.objects.create(owner=self.seller, balance=700)
        self.other_wallet = Wallet.objects.create(owner=self.other_user, balance=900)
        self.gym = Gym.objects.create(name="Commerce test gym")
        self.plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Monthly membership",
            description="Commerce test membership",
            duration_months=1,
            visit_limit=30,
            price=1200,
        )

    def make_order(self, **values):
        return Order.objects.create(
            **{
                "commerce_product": self.plan.id,
                "buyer": self.buyer,
                "seller": self.seller,
                "subtotal_amount": 1200,
                "discount_amount": 200,
                "tax_amount": 50,
                "product_snapshot": {"name": "Monthly membership", "visit_limit": 30},
                "status": Order.Status.SUCCEEDED,
                "succeeded_at": self.now,
                **values,
            }
        )

    def make_subscription(self, order, **values):
        subscription = GymSubscription.objects.create(
            **{
                "order": order,
                "subscriber": order.buyer,
                "plan": self.plan,
                "status": GymSubscription.Status.EXPIRED,
                "initial_visits": 30,
                "remaining_visits": 30,
                "duration_months": 1,
                "started_at": self.now - timedelta(days=31),
                "expires_at": self.now - timedelta(days=1),
                **values,
            }
        )
        GymSubscription.objects.filter(pk=subscription.pk).update(created_at=self.now - timedelta(days=31))
        subscription.refresh_from_db()
        return subscription

    def make_top_up(self, **values):
        return Payment.objects.create(
            **{
                "wallet": self.buyer_wallet,
                "purpose": Payment.Purpose.WALLET_TOP_UP,
                "payment_method": Payment.Method.ONLINE_GATEWAY,
                "amount": 1050,
                "gateway_fee_amount": 250000,
                "status": Payment.Status.PAID,
                "paid_at": self.now,
                **values,
            }
        )

    def make_order_payment(self, order, **values):
        return Payment.objects.create(
            **{
                "order": order,
                "purpose": Payment.Purpose.ORDER_PAYMENT,
                "payment_method": Payment.Method.ONLINE_GATEWAY,
                "amount": 1050,
                "gateway_fee_amount": 250000,
                "status": Payment.Status.PAID,
                "paid_at": self.now,
                **values,
            }
        )

    def run_competing_tasks(self, tasks, *, tables, before_query=False):
        barrier = Barrier(len(tasks))

        def worker(task):
            synchronized = False

            def synchronize(execute, sql, params, many, context):
                nonlocal synchronized
                matches = (
                    not synchronized
                    and sql.startswith("SELECT")
                    and any(f'FROM "{table}"' in sql for table in tables)
                    and (before_query or "FOR UPDATE" not in sql)
                )
                if matches and before_query:
                    barrier.wait(timeout=5)
                    synchronized = True
                result = execute(sql, params, many, context)
                if matches and not before_query:
                    # Both workers read the candidate snapshot before either processes it.
                    barrier.wait(timeout=5)
                    synchronized = True
                return result

            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                with connection.execute_wrapper(synchronize):
                    task()
                return synchronized
            finally:
                connections.close_all()

        with patch("gym_subscriptions.models.timezone.now", return_value=self.now):
            with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
                futures = [executor.submit(worker, task) for task in tasks]
                self.assertEqual([future.result(timeout=15) for future in futures], [True] * len(tasks))

    def test_two_settlement_workers_credit_same_order_once(self):
        order = self.make_order()
        self.make_subscription(order)
        payment = self.make_order_payment(order)
        self.run_competing_tasks(
            [process_seller_settlements, process_seller_settlements], tables=["order"]
        )

        self.seller_wallet.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.seller_wallet.balance, 1700)
        self.assertEqual(order.settlement_status, "RELEASED")
        entry = WalletLedger.objects.get()
        self.assertEqual(
            (entry.payment_id, entry.reason, entry.amount, entry.balance_before),
            (payment.pk, "SALE_REVENUE", 1000, 700),
        )

    def test_distinct_refund_and_sale_share_wallet_without_lost_credit(self):
        order = self.make_order()
        self.make_subscription(order)
        sale_payment = self.make_order_payment(order)
        refund_payment = self.make_top_up(wallet=self.seller_wallet)
        refund = Refund.objects.create_wallet_top_up_refund(refund_payment)
        # Different financial records contend for the same destination wallet.
        self.run_competing_tasks(
            [process_seller_settlements, process_pending_refunds], tables=["wallet"], before_query=True
        )

        self.seller_wallet.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.other_wallet.refresh_from_db()
        order.refresh_from_db()
        refund.refresh_from_db()
        self.assertEqual(self.seller_wallet.balance, 2750)
        self.assertEqual(self.buyer_wallet.balance, 5000)
        self.assertEqual(self.other_wallet.balance, 900)
        self.assertEqual(order.settlement_status, "RELEASED")
        self.assertEqual(refund.status, "COMPLETED")
        entries = list(WalletLedger.objects.order_by("balance_before"))
        self.assertEqual(len(entries), 2)
        self.assertEqual({entry.payment_id for entry in entries}, {sale_payment.pk, refund_payment.pk})
        self.assertEqual({entry.reason for entry in entries}, {"REFUND", "SALE_REVENUE"})
        self.assertEqual(
            {entry.payment_id: entry.amount for entry in entries}, {sale_payment.pk: 1000, refund_payment.pk: 1050}
        )
        self.assertTrue(
            all(entry.wallet_id == self.seller_wallet.pk and entry.entry_type == "CREDIT" for entry in entries)
        )
        self.assertEqual(entries[0].balance_before, 700)
        self.assertEqual(entries[1].balance_before, 700 + entries[0].amount)
        self.assertEqual(entries[1].balance_before + entries[1].amount, 2750)

    def test_approved_order_refund_and_settlement_cannot_both_credit(self):
        order = self.make_order()
        self.make_subscription(order)
        payment = self.make_order_payment(order)
        refund = Refund.objects.create(payment=payment, amount=1050)
        self.run_competing_tasks(
            [process_seller_settlements, process_pending_refunds], tables=["order", "refund"]
        )

        self.buyer_wallet.refresh_from_db()
        self.seller_wallet.refresh_from_db()
        order.refresh_from_db()
        refund.refresh_from_db()
        self.assertEqual(self.buyer_wallet.balance, 6050)
        self.assertEqual(self.seller_wallet.balance, 700)
        self.assertEqual(order.settlement_status, "VOIDED")
        self.assertEqual(refund.status, "COMPLETED")
        self.assertEqual(WalletLedger.objects.get().reason, "REFUND")
