from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from commerce_orders.models import Order
from commerce_products.models import CommerceProduct
from users.models import User


class OrderModelTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(phone_number="09120001001")
        self.product = CommerceProduct.objects.create(
            product_type=CommerceProduct.ProductType.GYM_MEMBERSHIP
        )

    def make_order(self, **overrides):
        return Order.objects.create(
            **{
                "buyer": self.buyer,
                "commerce_product": self.product,
                "product_snapshot": {"name": "Monthly"},
                "subtotal_amount": 100,
                "discount_amount": 10,
                "tax_amount": 5,
                "total_amount": 95,
                **overrides,
            }
        )

    def test_order_keeps_one_product_and_snapshot(self):
        order = self.make_order()

        self.assertEqual(order.pk.version, 7)
        self.assertEqual(order.commerce_product, self.product)
        self.assertEqual(order.product_snapshot, {"name": "Monthly"})
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_database_rejects_negative_amounts_on_insert_and_update(self):
        for field in ("subtotal_amount", "discount_amount", "tax_amount", "total_amount"):
            with self.subTest(field=field):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        self.make_order(**{field: -1})

                order = self.make_order()
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Order.objects.filter(pk=order.pk).update(**{field: -1})

    def test_zero_amounts_are_allowed(self):
        order = self.make_order(
            subtotal_amount=0, discount_amount=0, tax_amount=0, total_amount=0
        )
        self.assertEqual(order.total_amount, 0)