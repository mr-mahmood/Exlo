from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from commerce_orders.models import Order
from commerce_payments.models import Payment, PaymentGateway
from commerce_products.models import CommerceProduct
from commerce_wallet.models import Wallet
from users.models import User


class PaymentFixtures(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(phone_number="09120001003")
        self.wallet = Wallet.objects.create(owner=self.buyer)
        self.product = CommerceProduct.objects.create(product_type="GYM_MEMBERSHIP")
        self.order = Order.objects.create(
            buyer=self.buyer, commerce_product=self.product, product_snapshot={}
        )


class PaymentModelTests(PaymentFixtures):
    def test_valid_payment_methods_and_targets(self):
        top_up = Payment.objects.create_wallet_top_up(wallet=self.wallet, amount=100)
        wallet_payment = Payment.objects.create_order_payment_wallet(
            order=self.order, wallet=self.wallet, amount=100
        )
        gateway_payment = Payment.objects.create_order_payment_gateway(
            order=self.order, amount=100
        )

        self.assertEqual(top_up.purpose, Payment.Purpose.WALLET_TOP_UP)
        self.assertEqual(wallet_payment.gateway_fee_amount, 0)
        self.assertIsNone(gateway_payment.wallet_id)

    def test_database_rejects_nonpositive_amount_and_negative_fee(self):
        for overrides in ({"amount": 0}, {"amount": -1}, {"gateway_fee_amount": -1}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Payment.objects.create(**{
                            "wallet": self.wallet,
                            "purpose": Payment.Purpose.WALLET_TOP_UP,
                            "payment_method": Payment.Method.ONLINE_GATEWAY,
                            "amount": 100,
                            **overrides,
                        })

    def test_database_rejects_invalid_target_and_method_combinations(self):
        invalid = (
            {"purpose": "WALLET_TOP_UP", "payment_method": "WALLET", "wallet": self.wallet},
            {"purpose": "WALLET_TOP_UP", "payment_method": "ONLINE_GATEWAY", "order": self.order},
            {"purpose": "ORDER_PAYMENT", "payment_method": "ONLINE_GATEWAY", "order": self.order, "wallet": self.wallet},
            {"purpose": "ORDER_PAYMENT", "payment_method": "WALLET", "order": self.order, "wallet": self.wallet, "gateway_fee_amount": 1},
            {"purpose": "ORDER_PAYMENT", "payment_method": "WALLET", "wallet": self.wallet, "gateway_fee_amount": 0},
        )
        for fields in invalid:
            with self.subTest(fields=fields):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Payment.objects.create(amount=100, **fields)

    def test_only_one_succeeded_payment_per_order(self):
        first = Payment.objects.create_order_payment_gateway(order=self.order, amount=100)
        second = Payment.objects.create_order_payment_gateway(order=self.order, amount=100)
        first.mark_succeeded()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.filter(pk=second.pk).update(status=Payment.Status.SUCCEEDED)

        second.refresh_from_db()
        self.assertEqual(second.status, Payment.Status.PENDING)

    def test_database_rejects_invalid_target_after_update(self):
        payment = Payment.objects.create_wallet_top_up(wallet=self.wallet, amount=100)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.filter(pk=payment.pk).update(order=self.order)

        payment.refresh_from_db()
        self.assertIsNone(payment.order_id)

    def test_wallet_history_index_exists_in_database(self):
        with connection.cursor() as cursor:
            indexes = connection.introspection.get_constraints(cursor, Payment._meta.db_table)
        self.assertTrue(any(
            item["index"] and item["columns"] == ["wallet_id", "created_at"]
            for item in indexes.values()
        ))


class PaymentGatewayModelTests(PaymentFixtures):
    def test_unique_track_id_and_payment(self):
        payment = Payment.objects.create_wallet_top_up(wallet=self.wallet, amount=100)
        other_payment = Payment.objects.create_wallet_top_up(wallet=self.wallet, amount=100)
        PaymentGateway.objects.create(payment=payment, track_id=123)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PaymentGateway.objects.create(payment=other_payment, track_id=123)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PaymentGateway.objects.create(payment=payment, track_id=456)

    def test_mark_verified_persists_gateway_reference(self):
        payment = Payment.objects.create_wallet_top_up(wallet=self.wallet, amount=100)
        gateway = PaymentGateway.objects.create(payment=payment, track_id=123)

        gateway.mark_verified(ref_num="reference", card_number="1234")
        gateway.refresh_from_db()

        self.assertEqual(gateway.ref_num, "reference")
        self.assertEqual(gateway.card_number, "1234")
