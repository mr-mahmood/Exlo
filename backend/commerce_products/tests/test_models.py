from django.test import TestCase

from commerce_products.models import CommerceProduct


class CommerceProductModelTests(TestCase):
    def test_membership_product_has_uuid7_and_timestamp(self):
        product = CommerceProduct.objects.create(
            product_type=CommerceProduct.ProductType.GYM_MEMBERSHIP
        )

        self.assertEqual(product.pk.version, 7)
        self.assertIsNotNone(product.created_at)
        self.assertEqual(str(product), str(product.pk))
