# gym_plans/tests/test_serializers.py


import uuid
from django.test import TestCase
from gym.models import Gym
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

        self.other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="456 Other St",
        )

    def create_plan(self, **overrides):
        data = {
            "gym": self.gym,
            "name": "Premium Monthly",
            "description": "Unlimited access to all facilities",
            "duration_months": 1,
            "visit_limit": 4,
            "price": 49,
            "is_active": True,
        }
        data.update(overrides)

        return GymMembershipPlan.objects.create_plan(**data)

    def test_serializer_valid_data(self):
        """Test serializer with valid plan data."""
        plan = self.create_plan()

        serializer = GymMembershipPlanSerializer(plan)
        data = serializer.data

        self.assertEqual(data["name"], "Premium Monthly")
        self.assertEqual(data["price"], 49)
        self.assertEqual(data["duration_months"], 1)

    def test_serializer_includes_gym(self):
        """Test that the serializer includes the nested gym."""
        plan = self.create_plan()

        serializer = GymMembershipPlanSerializer(plan)
        data = serializer.data

        self.assertIn("gym", data)
        self.assertIsNotNone(data["gym"])

    def test_serializer_serializes_gym_correctly(self):
        """Test that gym is serialized using GymBasicSerializer."""
        plan = self.create_plan()

        serializer = GymMembershipPlanSerializer(plan)
        gym_data = serializer.data["gym"]

        self.assertEqual(gym_data["id"], str(self.gym.id))
        self.assertEqual(gym_data["name"], self.gym.name)
        self.assertEqual(gym_data["province"], self.gym.province)
        self.assertEqual(gym_data["city"], self.gym.city)
        self.assertEqual(gym_data["address"], self.gym.address)
        self.assertEqual(gym_data["is_active"], self.gym.is_active)

    def test_serializer_gym_contains_only_basic_fields(self):
        """Test that nested gym only exposes GymBasicSerializer fields."""
        plan = self.create_plan()

        serializer = GymMembershipPlanSerializer(plan)
        gym_data = serializer.data["gym"]

        expected_fields = {
            "id",
            "name",
            "province",
            "city",
            "address",
            "is_active",
        }

        self.assertEqual(set(gym_data.keys()), expected_fields)

    def test_serializer_fields(self):
        """Test serializer fields."""
        plan = self.create_plan()

        serializer = GymMembershipPlanSerializer(plan)
        data = serializer.data

        expected_fields = [
            "id",
            "name",
            "gym",
            "description",
            "duration_months",
            "visit_limit",
            "is_active",
            "price",
        ]

        for field in expected_fields:
            self.assertIn(field, data)

        self.assertEqual(data["name"], "Premium Monthly")
        self.assertEqual(data["price"], 49)
        self.assertEqual(data["duration_months"], 1)
        self.assertEqual(data["visit_limit"], 4)
        self.assertTrue(data["is_active"])

    def test_serializer_gym_is_read_only(self):
        """Test that gym cannot be changed through the serializer."""
        plan = self.create_plan()

        serializer = GymMembershipPlanSerializer(
            instance=plan,
            data={
                "gym": self.other_gym.id,
                "name": "Updated Name",
            },
            partial=True,
        )

        self.assertTrue(serializer.is_valid())

        updated_plan = serializer.save()
        updated_plan.refresh_from_db()

        self.assertEqual(updated_plan.gym_id, self.gym.id)
        self.assertEqual(updated_plan.name, "Updated Name")

    def test_serializer_gym_is_not_required_for_create(self):
        """Test that gym is not required in serializer input because it is read-only."""
        serializer = GymMembershipPlanSerializer(
            data={
                "name": "Test Plan",
                "description": "Test Description",
                "duration_months": 1,
                "visit_limit": 10,
                "price": 29,
                "is_active": True,
            }
        )

        self.assertTrue(serializer.is_valid())

    def test_serializer_read_only_fields(self):
        """Test that read-only fields are not writable."""
        plan = self.create_plan()

        data = {
            "id": str(uuid.uuid7()),
            "gym": self.other_gym.id,
            "name": "Updated Name",
        }

        serializer = GymMembershipPlanSerializer(
            instance=plan,
            data=data,
            partial=True,
        )

        self.assertTrue(serializer.is_valid())

        updated_plan = serializer.save()
        updated_plan.refresh_from_db()

        self.assertEqual(updated_plan.id, plan.id)
        self.assertEqual(updated_plan.gym_id, self.gym.id)
        self.assertEqual(updated_plan.name, "Updated Name")

    def test_serializer_update(self):
        """Test updating a plan through serializer."""
        plan = self.create_plan(
            name="Original Name",
            description="Original Description",
            price=29,
        )

        update_data = {
            "name": "Updated Name",
            "price": 59,
        }

        serializer = GymMembershipPlanSerializer(
            instance=plan,
            data=update_data,
            partial=True,
        )

        self.assertTrue(serializer.is_valid())

        updated_plan = serializer.save()
        updated_plan.refresh_from_db()

        self.assertEqual(updated_plan.name, "Updated Name")
        self.assertEqual(updated_plan.price, 59)
        self.assertEqual(updated_plan.description, "Original Description")
        self.assertEqual(updated_plan.gym_id, self.gym.id)

    def test_serializer_validation_errors(self):
        """Test serializer with missing required fields"""
        data = {
            "name": "Test",
            "duration_months": 1,
        }

        serializer = GymMembershipPlanSerializer(data=data)

        self.assertFalse(serializer.is_valid())

        self.assertIn("description", serializer.errors)
        self.assertIn("price", serializer.errors)

    def test_serializer_validation_invalid_price(self):
        """Test serializer with invalid price."""
        data = {
            "name": "Test Plan",
            "description": "Test Description",
            "duration_months": 1,
            "price": -10,
            "is_active": True,
        }

        serializer = GymMembershipPlanSerializer(data=data)

        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)

        self.assertEqual(
            context.exception.error_code,
            GymPlansError.INVALID_PRICE[0],
        )

    def test_serializer_validation_negative_duration(self):
        """Test serializer with negative duration."""
        data = {
            "name": "Test Plan",
            "description": "Test Description",
            "duration_months": -1,
            "price": 29,
            "is_active": True,
        }

        serializer = GymMembershipPlanSerializer(data=data)

        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)

        self.assertEqual(
            context.exception.error_code,
            GymPlansError.INVALID_DURATION[0],
        )

    def test_serializer_validation_negative_visit_limit(self):
        """Test serializer with negative visit limit."""
        data = {
            "name": "Test Plan",
            "description": "Test Description",
            "duration_months": 1,
            "visit_limit": -5,
            "price": 29,
            "is_active": True,
        }

        serializer = GymMembershipPlanSerializer(data=data)

        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)

        self.assertEqual(
            context.exception.error_code,
            GymPlansError.INVALID_VISIT_LIMIT[0],
        )

    def test_serializer_rejects_numbers_above_storage_limits(self):
        for field, overflow in (
            ("duration_months", 2_147_483_648),
            ("visit_limit", 2_147_483_648),
            ("price", 9_223_372_036_854_775_808),
        ):
            for value in (overflow, str(overflow)):
                with self.subTest(field=field, value=value):
                    data = {
                        "name": "Test Plan",
                        "description": "Test Description",
                        "duration_months": 1,
                        "visit_limit": 10,
                        "price": 29,
                        field: value,
                    }
                    serializer = GymMembershipPlanSerializer(data=data)
                    with self.assertNumQueries(0):
                        self.assertFalse(serializer.is_valid())
                    self.assertIn(field, serializer.errors)

    def test_serializer_accepts_numeric_boundaries(self):
        for values in (
            {"duration_months": 1, "visit_limit": 5, "price": 1},
            {
                "duration_months": 2_147_483_647,
                "visit_limit": 2_147_483_647,
                "price": 9_223_372_036_854_775_807,
            },
        ):
            with self.subTest(values=values):
                serializer = GymMembershipPlanSerializer(
                    data={
                        "name": "Boundary Plan",
                        "description": "Boundary",
                        **values,
                    }
                )
                self.assertTrue(serializer.is_valid(), serializer.errors)

                for field, value in values.items():
                    self.assertEqual(serializer.validated_data[field], value)

    def test_serializer_rejects_visit_limit_at_or_below_four(self):
        """Visit limits of 4 or less must be rejected."""
        for visit_limit in (0, 1, 2, 3):
            with self.subTest(visit_limit=visit_limit):
                serializer = GymMembershipPlanSerializer(
                    data={
                        "name": "Test Plan",
                        "description": "Test Description",
                        "duration_months": 1,
                        "visit_limit": visit_limit,
                        "price": 29,
                    }
                )

                with self.assertRaises(APIError) as context:
                    serializer.is_valid(raise_exception=True)

                self.assertEqual(
                    context.exception.error_code,
                    GymPlansError.INVALID_VISIT_LIMIT[0],
                )

    def test_serializer_accepts_visit_limit_above_four(self):
        """Visit limits greater than 4 must be accepted."""
        for visit_limit in (5, 6, 10):
            with self.subTest(visit_limit=visit_limit):
                serializer = GymMembershipPlanSerializer(
                    data={
                        "name": "Test Plan",
                        "description": "Test Description",
                        "duration_months": 1,
                        "visit_limit": visit_limit,
                        "price": 29,
                    }
                )

                self.assertTrue(serializer.is_valid(), serializer.errors)
                self.assertEqual(
                    serializer.validated_data["visit_limit"],
                    visit_limit,
                )

    def test_numeric_fields_remain_required_and_non_nullable(self):
        data = {
            "name": "Test Plan",
            "description": "Test Description",
            "duration_months": 1,
            "visit_limit": 10,
            "price": 29,
        }
        for field in ("duration_months", "visit_limit", "price"):
            with self.subTest(field=field, case="missing"):
                missing = {name: value for name, value in data.items() if name != field}
                serializer = GymMembershipPlanSerializer(data=missing)
                self.assertFalse(serializer.is_valid())
                self.assertIn(field, serializer.errors)
            with self.subTest(field=field, case="null"):
                serializer = GymMembershipPlanSerializer(data={**data, field: None})
                self.assertFalse(serializer.is_valid())
                self.assertIn(field, serializer.errors)

    def test_non_positive_numbers_keep_existing_error_codes(self):
        for field, error_code in (
            ("duration_months", GymPlansError.INVALID_DURATION[0]),
            ("visit_limit", GymPlansError.INVALID_VISIT_LIMIT[0]),
            ("price", GymPlansError.INVALID_PRICE[0]),
        ):
            for value in (0, -1):
                with self.subTest(field=field, value=value):
                    serializer = GymMembershipPlanSerializer(
                        data={
                            "name": "Test Plan",
                            "description": "Test Description",
                            "duration_months": 1,
                            "visit_limit": 10,
                            "price": 29,
                            field: value,
                        }
                    )
                    with self.assertRaises(APIError) as raised:
                        serializer.is_valid(raise_exception=True)
                    self.assertEqual(raised.exception.error_code, error_code)
