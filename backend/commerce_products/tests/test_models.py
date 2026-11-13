from django.test import TestCase

from commerce_products.models import CommerceProduct
from gym.models import Gym
from gym_plans.models import GymMembershipPlan


class CommerceProductModelTests(TestCase):
    def test_manager_creates_distinct_membership_products(self):
        first = CommerceProduct.objects.create_gym_membership_product()
        second = CommerceProduct.objects.create_gym_membership_product()

        first.refresh_from_db()
        self.assertEqual(first.product_type, "GYM_MEMBERSHIP")
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.pk.version, 7)
        self.assertEqual(CommerceProduct.objects.count(), 2)

    def test_membership_plan_links_to_product_in_both_directions(self):
        plan = GymMembershipPlan.objects.create_plan(
            gym=Gym.objects.create(name="Product test gym"),
            name="Monthly membership",
            description="Product test",
            duration_months=1,
            visit_limit=30,
            price=1200,
        )

        product = CommerceProduct.objects.get(pk=plan.pk)
        self.assertEqual(product.product_type, "GYM_MEMBERSHIP")
        self.assertEqual(product.gym_membership_plan, plan)
        self.assertEqual(plan.id, product)
