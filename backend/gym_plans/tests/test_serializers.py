# gym_plans/tests/test_serializers.py
# type: ignore

import uuid
from decimal import Decimal
from django.test import TestCase
from users.models import User
from gym.models import Gym
from commerce_products.models import CommerceProduct
from gym_plans.models import GymMembershipPlan
from gym_plans.serializers import GymMembershipPlanSerializer
from core.errors import APIError, GymPlansError


class GymMembershipPlanSerializerTest(TestCase):
    """Test cases for GymMembershipPlanSerializer."""

    def setUp(self):
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
        )
        self.plan_data = {
            "gym": self.gym.id,
            "name": "Premium Monthly",
            "description": "Unlimited access to all facilities",
            "duration_month": 1,
            "visit_limit": 0,
            "price": "49.99",
            "is_active": True,
        }

    def test_serializer_valid_data(self):
        """Test serializer with valid data."""
        commerce_product = CommerceProduct.objects.create(
            product_type=CommerceProduct.ProductType.GYM_MEMBERSHIP
        )

        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Premium Monthly",
            description="Unlimited access to all facilities",
            duration_month=1,
            visit_limit=0,
            price=Decimal("49.99"),
            is_active=True,
        )

        # Then serialize it
        serializer = GymMembershipPlanSerializer(plan)
        data = serializer.data

        self.assertEqual(data["name"], "Premium Monthly")
        self.assertEqual(data["price"], "49.99")
        self.assertEqual(data["duration_month"], 1)

    def test_serializer_read_only_fields(self):
        """Test that read-only fields are not writable."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Test Plan",
            description="Test Description",
            duration_month=1,
            price=Decimal("29.99"),
            is_active=True,
        )

        # Try to update with read-only fields
        data = {
            "id": str(uuid.uuid4()),  # Should be ignored
            "name": "Updated Name",
        }

        serializer = GymMembershipPlanSerializer(
            instance=plan,
            data=data,
            partial=True,
        )
        self.assertTrue(serializer.is_valid())

        updated_plan = serializer.save()
        # id should not change
        self.assertEqual(updated_plan.id, plan.id)
        self.assertEqual(updated_plan.name, "Updated Name")

    def test_serializer_fields(self):
        """Test serializer fields."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Premium Monthly",
            description="Unlimited access",
            duration_month=1,
            visit_limit=0,
            price=Decimal("49.99"),
            is_active=True,
        )

        serializer = GymMembershipPlanSerializer(plan)
        data = serializer.data

        expected_fields = [
            "id",
            "name",
            "description",
            "duration_month",
            "visit_limit",
            "is_active",
            "price",
        ]

        for field in expected_fields:
            self.assertIn(field, data)

        self.assertEqual(data["name"], "Premium Monthly")
        self.assertEqual(data["price"], "49.99")
        self.assertEqual(data["duration_month"], 1)
        self.assertEqual(data["visit_limit"], 0)
        self.assertTrue(data["is_active"])

    def test_serializer_update(self):
        """Test updating a plan through serializer."""
        plan = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Original Name",
            description="Original Description",
            duration_month=1,
            price=Decimal("29.99"),
        )

        update_data = {
            "name": "Updated Name",
            "price": "59.99",
        }

        serializer = GymMembershipPlanSerializer(
            instance=plan,
            data=update_data,
            partial=True,
        )
        self.assertTrue(serializer.is_valid())

        updated_plan = serializer.save()
        self.assertEqual(updated_plan.name, "Updated Name")
        self.assertEqual(updated_plan.price, Decimal("59.99"))
        self.assertEqual(updated_plan.description, "Original Description")

    def test_serializer_validation_errors(self):
        """Test serializer validation errors."""
        # Missing required fields (description, price)
        data = {
            "name": "Test",
            "duration_month": 1,
        }

        serializer = GymMembershipPlanSerializer(data=data)
        self.assertFalse(serializer.is_valid())

        self.assertIn("description", serializer.errors)
        self.assertIn("price", serializer.errors)

    def test_serializer_validation_invalid_price(self):
        """Test serializer with invalid price (negative)."""
        data = {
            "gym": self.gym.id,
            "name": "Test Plan",
            "description": "Test Description",
            "duration_month": 1,
            "price": "-10.00",
            "is_active": True,
        }

        serializer = GymMembershipPlanSerializer(data=data)

        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)

        self.assertEqual(context.exception.args[0][0], GymPlansError.INVALID_PRICE[0])

    def test_serializer_validation_negative_duration(self):
        """Test serializer with negative duration."""
        data = {
            "gym": self.gym.id,
            "name": "Test Plan",
            "description": "Test Description",
            "duration_month": -1,
            "price": "29.99",
            "is_active": True,
        }

        serializer = GymMembershipPlanSerializer(data=data)

        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)

        self.assertEqual(
            context.exception.args[0][0], GymPlansError.INVALID_DURATION[0]
        )

    def test_serializer_validation_negative_visit_limit(self):
        """Test serializer with negative visit limit."""
        data = {
            "gym": self.gym.id,
            "name": "Test Plan",
            "description": "Test Description",
            "duration_month": 1,
            "visit_limit": -5,
            "price": "29.99",
            "is_active": True,
        }

        serializer = GymMembershipPlanSerializer(data=data)

        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)

        self.assertEqual(
            context.exception.args[0][0], GymPlansError.INVALID_VISIT_LIMIT[0]
        )
