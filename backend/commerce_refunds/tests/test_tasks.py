from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from unittest.mock import patch

from django.db import connection, connections
from django.test import TestCase, TransactionTestCase

from commerce_orders.models import Order
from commerce_payments.models import Payment
from commerce_refunds.models import Refund
from commerce_refunds.tasks import process_pending_refunds
from commerce_wallet.models import Wallet
from commerce_wallet_ledger.models import WalletLedger
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from users.models import User


class PendingRefundTaskTests(TestCase):
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

    def run_task(self):
        with patch("commerce_refunds.models.timezone.now", return_value=self.now):
            process_pending_refunds()

    def make_order_refund(self, **payment_values):
        order = self.make_order()
        payment = self.make_order_payment(order, **payment_values)
        refund = Refund.objects.create(payment=payment, amount=1050)
        return order, payment, refund

    def assert_pending_without_credit(self, refund):
        refund.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.seller_wallet.refresh_from_db()
        self.other_wallet.refresh_from_db()
        self.assertEqual(refund.status, "PENDING")
        self.assertIsNone(refund.refunded_at)
        self.assertEqual(self.buyer_wallet.balance, 5000)
        self.assertEqual(self.seller_wallet.balance, 700)
        self.assertEqual(self.other_wallet.balance, 900)
        self.assertFalse(WalletLedger.objects.exists())

    def assert_completed(self, refund, payment):
        refund.refresh_from_db()
        payment.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.seller_wallet.refresh_from_db()
        self.other_wallet.refresh_from_db()
        self.assertEqual(refund.status, "COMPLETED")
        self.assertEqual(refund.refunded_at, self.now)
        self.assertEqual(payment.status, "PAID")
        self.assertEqual(self.buyer_wallet.balance, 6050)
        self.assertEqual(self.seller_wallet.balance, 700)
        self.assertEqual(self.other_wallet.balance, 900)
        entry = WalletLedger.objects.get(payment=payment, reason="REFUND")
        self.assertEqual(
            (entry.wallet_id, entry.entry_type, entry.amount, entry.balance_before),
            (self.buyer_wallet.pk, "CREDIT", 1050, 5000),
        )

    def test_top_up_refund_credits_payment_wallet_without_gateway_fee(self):
        payment = self.make_top_up()
        refund = Refund.objects.create_wallet_top_up_refund(payment)
        self.run_task()

        self.assert_completed(refund, payment)
        self.assertEqual(WalletLedger.objects.count(), 1)

    def test_gateway_order_refund_credits_buyer_and_voids_seller_settlement(self):
        order, payment, refund = self.make_order_refund()
        self.run_task()

        self.assert_completed(refund, payment)
        order.refresh_from_db()
        self.assertEqual(order.status, "SUCCEEDED")
        self.assertEqual(order.settlement_status, "VOIDED")

    def test_wallet_order_refund_credits_buyer_and_voids_seller_settlement(self):
        order, payment, refund = self.make_order_refund(
            payment_method="WALLET", wallet=self.buyer_wallet, gateway_fee_amount=0
        )
        self.run_task()

        self.assert_completed(refund, payment)
        order.refresh_from_db()
        self.assertEqual(order.settlement_status, "VOIDED")

    def test_order_refund_destination_is_buyer_instead_of_another_wallet(self):
        order, payment, refund = self.make_order_refund(
            payment_method="WALLET", wallet=self.other_wallet, gateway_fee_amount=0
        )
        self.run_task()

        self.assert_completed(refund, payment)
        order.refresh_from_db()
        self.assertEqual(order.settlement_status, "VOIDED")

    def test_top_up_refund_uses_its_own_wallet_owner(self):
        payment = self.make_top_up(wallet=self.other_wallet)
        refund = Refund.objects.create_wallet_top_up_refund(payment)
        self.run_task()

        self.other_wallet.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        refund.refresh_from_db()
        self.assertEqual(self.other_wallet.balance, 1950)
        self.assertEqual(self.buyer_wallet.balance, 5000)
        self.assertEqual(refund.status, "COMPLETED")
        self.assertEqual(WalletLedger.objects.get().wallet_id, self.other_wallet.pk)

    def test_approved_refund_does_not_recheck_eligibility_or_cancel_product(self):
        order, payment, refund = self.make_order_refund()
        subscription = self.make_subscription(order)
        self.assertFalse(order.is_refundable)
        before = GymSubscription.objects.filter(pk=subscription.pk).values().get()
        self.run_task()

        self.assert_completed(refund, payment)
        subscription.refresh_from_db()
        self.assertEqual(GymSubscription.objects.filter(pk=subscription.pk).values().get(), before)

    def test_repeated_execution_preserves_all_financial_records_and_timestamps(self):
        order, payment, refund = self.make_order_refund()
        self.run_task()
        before = (
            list(Wallet.objects.order_by("pk").values()),
            list(WalletLedger.objects.values()),
            list(Refund.objects.values()),
            list(Order.objects.values()),
        )
        self.run_task()

        self.assertEqual(
            (
                list(Wallet.objects.order_by("pk").values()),
                list(WalletLedger.objects.values()),
                list(Refund.objects.values()),
                list(Order.objects.values()),
            ),
            before,
        )

    def test_pending_and_failed_payments_are_not_refunded(self):
        payment = self.make_top_up(status="PENDING", paid_at=None)
        refund = Refund.objects.create_wallet_top_up_refund(payment)
        for status in ("PENDING", "FAILED"):
            with self.subTest(status=status):
                Payment.objects.filter(pk=payment.pk).update(status=status)
                self.run_task()
                self.assert_pending_without_credit(refund)

    def test_partial_and_excessive_refunds_are_not_processed(self):
        payment = self.make_top_up()
        refund = Refund.objects.create_wallet_top_up_refund(payment)
        for amount in (1049, 1051, 251050):
            with self.subTest(amount=amount):
                Refund.objects.filter(pk=refund.pk).update(amount=amount)
                self.run_task()
                self.assert_pending_without_credit(refund)

    def test_unsuccessful_orders_leave_refund_pending_and_settlement_held(self):
        order, payment, refund = self.make_order_refund()
        for status in ("PENDING", "FAILED"):
            with self.subTest(status=status):
                Order.objects.filter(pk=order.pk).update(status=status)
                self.run_task()
                self.assert_pending_without_credit(refund)
                order.refresh_from_db()
                self.assertEqual(order.settlement_status, "HELD")

    def test_released_and_voided_settlements_cannot_be_refunded_again(self):
        order, payment, refund = self.make_order_refund()
        for settlement in ("RELEASED", "VOIDED"):
            with self.subTest(settlement=settlement):
                Order.objects.filter(pk=order.pk).update(settlement_status=settlement)
                self.run_task()
                self.assert_pending_without_credit(refund)
                order.refresh_from_db()
                self.assertEqual(order.settlement_status, settlement)

    def test_completed_refund_is_not_credited_or_retimestamped(self):
        refund = Refund.objects.create(
            payment=self.make_top_up(), amount=1050, status="COMPLETED", refunded_at=self.now
        )
        before = Refund.objects.get(pk=refund.pk).updated_at
        self.run_task()
        refund.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.assertEqual(refund.refunded_at, self.now)
        self.assertEqual(refund.updated_at, before)
        self.assertEqual(self.buyer_wallet.balance, 5000)
        self.assertFalse(WalletLedger.objects.exists())

    def test_missing_buyer_wallet_leaves_order_refund_pending(self):
        order, payment, refund = self.make_order_refund()
        self.buyer_wallet.delete()
        self.run_task()
        refund.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(refund.status, "PENDING")
        self.assertIsNone(refund.refunded_at)
        self.assertEqual(order.settlement_status, "HELD")
        self.assertFalse(Wallet.objects.filter(owner=self.buyer).exists())
        self.assertFalse(WalletLedger.objects.exists())

    def test_ledger_failure_rolls_back_wallet_credit_and_voided_settlement(self):
        order, payment, refund = self.make_order_refund()
        with patch.object(
            WalletLedger.objects, "create_refund_ledger", side_effect=RuntimeError("insert failed")
        ) as failure:
            self.run_task()
        failure.assert_called_once()
        self.assert_pending_without_credit(refund)
        order.refresh_from_db()
        self.assertEqual(order.settlement_status, "HELD")

    def test_completion_failure_rolls_back_ledger_wallet_and_settlement(self):
        order, payment, refund = self.make_order_refund()
        with patch.object(Refund, "mark_completed", side_effect=RuntimeError("update failed")) as failure:
            self.run_task()
        failure.assert_called_once()
        self.assert_pending_without_credit(refund)
        order.refresh_from_db()
        self.assertEqual(order.settlement_status, "HELD")

    def test_top_up_ledger_failure_rolls_back_wallet_credit(self):
        refund = Refund.objects.create_wallet_top_up_refund(self.make_top_up())
        with patch.object(
            WalletLedger.objects, "create_refund_ledger", side_effect=RuntimeError("insert failed")
        ) as failure:
            self.run_task()
        failure.assert_called_once()
        self.assert_pending_without_credit(refund)

    def test_existing_refund_ledger_prevents_a_second_wallet_credit(self):
        payment = self.make_top_up()
        refund = Refund.objects.create_wallet_top_up_refund(payment)
        self.buyer_wallet.credit(1050)
        WalletLedger.objects.create_refund_ledger(
            wallet=self.buyer_wallet, payment=payment, amount=1050, balance_before=5000
        )
        self.run_task()

        self.buyer_wallet.refresh_from_db()
        refund.refresh_from_db()
        self.assertEqual(self.buyer_wallet.balance, 6050)
        self.assertEqual(refund.status, "PENDING")
        self.assertEqual(WalletLedger.objects.count(), 1)

    def test_failure_does_not_block_other_refunds_and_retry_credits_only_failed_item(self):
        good = Refund.objects.create_wallet_top_up_refund(self.make_top_up())
        bad = Refund.objects.create_wallet_top_up_refund(self.make_top_up())
        create_ledger = WalletLedger.objects.create_refund_ledger

        def fail_one_payment(**values):
            if values["payment"].pk == bad.payment_id:
                raise RuntimeError("one ledger insert failed")
            return create_ledger(**values)

        with patch.object(WalletLedger.objects, "create_refund_ledger", side_effect=fail_one_payment):
            self.run_task()
        good.refresh_from_db()
        bad.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.assertEqual(good.status, "COMPLETED")
        self.assertEqual(bad.status, "PENDING")
        self.assertEqual(self.buyer_wallet.balance, 6050)
        self.assertEqual(WalletLedger.objects.get().payment_id, good.payment_id)

        self.run_task()
        bad.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.assertEqual(bad.status, "COMPLETED")
        self.assertEqual(self.buyer_wallet.balance, 7100)
        self.assertEqual(WalletLedger.objects.count(), 2)

    def test_empty_refund_batch_changes_nothing(self):
        self.run_task()
        self.buyer_wallet.refresh_from_db()
        self.assertEqual(self.buyer_wallet.balance, 5000)
        self.assertFalse(Refund.objects.exists())
        self.assertFalse(WalletLedger.objects.exists())


class PendingRefundConcurrencyTests(TransactionTestCase):
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

    def test_two_refund_workers_credit_same_top_up_once(self):
        payment = self.make_top_up()
        refund = Refund.objects.create_wallet_top_up_refund(payment)
        self.run_competing_tasks([process_pending_refunds, process_pending_refunds], tables=["refund"])

        refund.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.assertEqual(refund.status, "COMPLETED")
        self.assertEqual(refund.refunded_at, self.now)
        self.assertEqual(self.buyer_wallet.balance, 6050)
        entry = WalletLedger.objects.get()
        self.assertEqual(
            (entry.payment_id, entry.reason, entry.amount, entry.balance_before),
            (payment.pk, "REFUND", 1050, 5000),
        )

    def test_two_order_refund_workers_credit_buyer_and_void_settlement_once(self):
        order = self.make_order()
        payment = self.make_order_payment(order)
        refund = Refund.objects.create(payment=payment, amount=1050)
        self.run_competing_tasks([process_pending_refunds, process_pending_refunds], tables=["refund"])

        refund.refresh_from_db()
        order.refresh_from_db()
        self.buyer_wallet.refresh_from_db()
        self.seller_wallet.refresh_from_db()
        self.assertEqual(refund.status, "COMPLETED")
        self.assertEqual(order.settlement_status, "VOIDED")
        self.assertEqual(self.buyer_wallet.balance, 6050)
        self.assertEqual(self.seller_wallet.balance, 700)
        self.assertEqual(WalletLedger.objects.get().reason, "REFUND")
