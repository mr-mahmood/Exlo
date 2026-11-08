from django.db import IntegrityError, transaction
from django.test import TestCase

from commerce_orders.models import Order
from commerce_payments.models import Payment
from commerce_products.models import CommerceProduct
from commerce_refunds.models import Refund
from users.models import User


class RefundModelTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(phone_number="09120001004")
        self.product = CommerceProduct.objects.create(product_type="GYM_MEMBERSHIP")
        self.order = Order.objects.create(
            buyer=self.buyer, commerce_product=self.product, product_snapshot={}
        )
        self.payment = Payment.objects.create_order_payment_gateway(
            order=self.order, amount=100
        )

    def make_refund(self, **overrides):
        return Refund.objects.create(**{
            "order": self.order,
            "payment": self.payment,
            "amount": 100,
            "request_reason": "Cancellation",
            **overrides,
        })

    def test_refund_has_review_state_and_uuid7(self):
        refund = self.make_refund()
        self.assertEqual(refund.pk.version, 7)
        self.assertEqual(refund.status, Refund.Status.PENDING_REVIEW)
        self.assertEqual(refund.amount, 100)

    def test_database_rejects_nonpositive_amount_on_insert_and_update(self):
        for amount in (0, -1):
            with self.subTest(amount=amount):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        self.make_refund(amount=amount)

        refund = self.make_refund()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Refund.objects.filter(pk=refund.pk).update(amount=0)

    def test_order_and_payment_can_each_be_refunded_once(self):
        self.make_refund()
        second_order = Order.objects.create(
            buyer=self.buyer, commerce_product=self.product, product_snapshot={}
        )
        second_payment = Payment.objects.create_order_payment_gateway(
            order=second_order, amount=100
        )

        for fields in (
            {"payment": second_payment},
            {"order": second_order},
        ):
            with self.subTest(fields=fields):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        self.make_refund(**fields)
