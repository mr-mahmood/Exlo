# gym_plans/tests/test_models.py


import time
from django.db import DataError, IntegrityError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from gym.models import Gym
from commerce_products.models import CommerceProduct
from gym_plans.models import GymMembershipPlan


class GymMembershipPlanModelTest(TestCase):
    """Test cases for GymMembershipPlan model."""

    def setUp(self):
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
        )

    def test_create_plan_success(self):
        """Test creating a plan successfully using manager."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Premium Monthly",
            description="Unlimited access",
            duration_months=1,
            visit_limit=0,
            price=49,
            is_active=True,
        )

        self.assertIsNotNone(plan.id)
        self.assertEqual(plan.gym, self.gym)
        self.assertEqual(plan.name, "Premium Monthly")
        self.assertEqual(plan.description, "Unlimited access")
        self.assertEqual(plan.duration_months, 1)
        self.assertEqual(plan.visit_limit, 0)
        self.assertEqual(plan.price, 49)
        self.assertTrue(plan.is_active)
        self.assertIsNone(plan.deleted_at)
        self.assertIsInstance(plan.id, CommerceProduct)

    def test_create_plan_creates_commerce_product(self):
        """Test that create_plan automatically creates a CommerceProduct."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Test Plan",
            description="Test Description",
            duration_months=1,
            price=29,
        )

        # Check that CommerceProduct was created
        self.assertIsNotNone(plan.id)
        self.assertEqual(
            plan.id.product_type, CommerceProduct.ProductType.GYM_MEMBERSHIP
        )

        # Check that we can access the commerce product
        commerce_product = CommerceProduct.objects.get(id=plan.id.id)
        self.assertEqual(
            commerce_product.product_type, CommerceProduct.ProductType.GYM_MEMBERSHIP
        )

    def test_plan_str_method(self):
        """Test the __str__ method of GymMembershipPlan."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Premium Monthly",
            description="Unlimited access",
            duration_months=1,
            price=49,
        )

        expected = f"{plan.name} - {plan.gym.name}"
        self.assertEqual(str(plan), expected)

    def test_is_deleted_property(self):
        """Test the is_deleted property."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Test Plan",
            description="Test Description",
            duration_months=1,
            price=29,
        )

        self.assertFalse(plan.is_deleted)

        plan.soft_delete()
        self.assertTrue(plan.is_deleted)

    def test_is_available_property(self):
        """Test the is_available property."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Test Plan",
            description="Test Description",
            duration_months=1,
            price=29,
            is_active=True,
        )

        self.assertTrue(plan.is_available)

        plan.soft_delete()
        self.assertFalse(plan.is_available)

        # Deactivate without deleting
        plan2 = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Test Plan 2",
            description="Test Description",
            duration_months=1,
            price=29,
            is_active=False,
        )
        self.assertFalse(plan2.is_available)

    def test_soft_delete(self):
        """Test soft delete functionality."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Test Plan",
            description="Test Description",
            duration_months=1,
            price=29,
        )

        self.assertIsNone(plan.deleted_at)
        self.assertTrue(plan.is_active)

        plan.soft_delete()

        self.assertIsNotNone(plan.deleted_at)
        self.assertFalse(plan.is_active)
        self.assertTrue(plan.is_deleted)

    def test_get_plan_active_only(self):
        """Test get_plan with active_only=True."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Active Plan",
            description="Active",
            duration_months=1,
            price=29,
            is_active=True,
        )

        retrieved = GymMembershipPlan.objects.get_plan(
            plan_id=plan.id,
            gym=self.gym,
            active_only=True,
        )

        self.assertEqual(retrieved.id, plan.id)

        # Delete the plan
        plan.soft_delete()

        # Should raise error when trying to get deleted plan with active_only=True
        with self.assertRaises(Exception):
            GymMembershipPlan.objects.get_plan(
                plan_id=plan.id,
                gym=self.gym,
                active_only=True,
            )

    def test_get_plan_inactive(self):
        """Test get_plan with active_only=False (can get deleted plans)."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Deleted Plan",
            description="Will be deleted",
            duration_months=1,
            price=29,
        )

        plan.soft_delete()

        # Should be able to get deleted plan with active_only=False
        retrieved = GymMembershipPlan.objects.get_plan(
            plan_id=plan.id,
            gym=self.gym,
            active_only=False,
        )

        self.assertEqual(retrieved.id, plan.id)
        self.assertTrue(retrieved.is_deleted)

    def test_get_gym_plans_active_only(self):
        """Test get_gym_plans with active_only=True."""
        # Create multiple plans
        plan1 = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Plan 1",
            description="Active",
            duration_months=1,
            price=29,
            is_active=True,
        )
        plan2 = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Plan 2",
            description="Active",
            duration_months=1,
            price=39,
            is_active=True,
        )
        plan3 = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Plan 3",
            description="Deleted",
            duration_months=1,
            price=49,
            is_active=True,
        )
        plan3.soft_delete()

        plans = GymMembershipPlan.objects.get_gym_plans(
            gym=self.gym,
            active_only=True,
        )

        self.assertEqual(plans.count(), 2)
        plan_ids = [p.id for p in plans]
        self.assertIn(plan1.id, plan_ids)
        self.assertIn(plan2.id, plan_ids)
        self.assertNotIn(plan3.id, plan_ids)

    def test_get_gym_plans_all(self):
        """Test get_gym_plans with active_only=False (includes deleted)."""
        plan1 = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Plan 1",
            description="Active",
            duration_months=1,
            price=29,
        )
        plan2 = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Plan 2",
            description="Deleted",
            duration_months=1,
            price=39,
        )
        plan2.soft_delete()

        plans = GymMembershipPlan.objects.get_gym_plans(
            gym=self.gym,
            active_only=False,
        )

        self.assertEqual(plans.count(), 2)
        plan_ids = [p.id for p in plans]
        self.assertIn(plan1.id, plan_ids)
        self.assertIn(plan2.id, plan_ids)

    def test_plan_created_timestamp(self):
        """Test that created_at is auto-set."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Test Plan",
            description="Test",
            duration_months=1,
            price=29,
        )

        self.assertIsNotNone(plan.created_at)
        self.assertLess(plan.created_at, timezone.now() + timezone.timedelta(seconds=1))

    def test_plan_updated_timestamp(self):
        """Test that updated_at updates on save."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Test Plan",
            description="Test",
            duration_months=1,
            price=29,
        )

        original_updated = plan.updated_at

        time.sleep(0.1)

        # Update the plan
        plan.name = "Updated Name"
        plan.save()

        self.assertGreater(plan.updated_at, original_updated)


class GymMembershipPlanCreationTransactionTests(TransactionTestCase):
    def setUp(self):
        self.gym = Gym.objects.create(
            name="Test Gym", province="Tehran", city="Tehran", address="Address"
        )
        self.create_plan()

    def create_plan(self, **overrides):
        return GymMembershipPlan.objects.create_plan(
            **{
                "gym": self.gym,
                "name": "Test Plan",
                "description": "Test Description",
                "duration_months": 1,
                "visit_limit": 10,
                "price": 29,
                **overrides,
            }
        )

    def assert_failed_creation_is_atomic(self, error, **overrides):
        products = set(CommerceProduct.objects.values_list("pk", flat=True))
        plans = set(GymMembershipPlan.objects.values_list("pk", flat=True))
        # Autocommit exposes orphan products that an outer test transaction would hide.
        with self.assertRaises(error):
            self.create_plan(**overrides)
        self.assertEqual(
            set(CommerceProduct.objects.values_list("pk", flat=True)), products
        )
        self.assertEqual(
            set(GymMembershipPlan.objects.values_list("pk", flat=True)), plans
        )

    def test_oversized_duration_does_not_leave_orphan_product(self):
        self.assert_failed_creation_is_atomic(DataError, duration_months=2_147_483_648)

    def test_other_plan_insert_failures_do_not_leave_orphan_products(self):
        for error, overrides in (
            (DataError, {"visit_limit": 2_147_483_648}),
            (DataError, {"price": 9_223_372_036_854_775_808}),
            (IntegrityError, {"gym": None}),
        ):
            with self.subTest(overrides=overrides):
                self.assert_failed_creation_is_atomic(error, **overrides)
