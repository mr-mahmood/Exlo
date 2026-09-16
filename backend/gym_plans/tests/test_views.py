# gym_plans/tests/test_views.py
# type: ignore

import uuid
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from users.models import User
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_auth.models import UserGymRole
from commerce_products.models import CommerceProduct
from django.conf import settings


class GymPlansViewsTest(TestCase):
    """Test cases for GymPlans views."""

    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()

        # Create users
        self.admin_user = User.objects.create_superuser(
            phone_number="09121234567",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
        )

        self.gym_owner = User.objects.create_user(
            phone_number="09129876543",
            first_name="Owner",
            last_name="User",
        )

        self.regular_user = User.objects.create_user(
            phone_number="09121112222",
            first_name="Regular",
            last_name="User",
        )

        # Create gym
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
            is_active=True,
        )

        # Make gym_owner the owner of the gym
        UserGymRole.objects.create(
            user=self.gym_owner,
            gym=self.gym,
            role=UserGymRole.Role.OWNER,
        )

        # Create some plans
        self.plan1 = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Basic Monthly",
            description="Basic plan with limited visits",
            duration_months=1,
            visit_limit=10,
            price=Decimal("29.99"),
            is_active=True,
        )

        self.plan2 = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Premium Monthly",
            description="Unlimited access",
            duration_months=1,
            visit_limit=0,
            price=Decimal("49.99"),
            is_active=True,
        )

        self.plan3 = GymMembershipPlan.objects.create_plan(
            gym=self.gym,
            name="Yearly Premium",
            description="Yearly unlimited access",
            duration_months=12,
            visit_limit=0,
            price=Decimal("499.99"),
            is_active=False,  # Inactive
        )

        self.list_url = reverse("gym_plans:list", kwargs={"gym_id": self.gym.id})
        self.create_url = reverse("gym_plans:create", kwargs={"gym_id": self.gym.id})

    def authenticate(self, user):
        """Helper to authenticate a user."""
        self.client.force_authenticate(user=user)

    # ==================== LIST TESTS ====================

    def test_list_plans_public_access(self):
        """Test that plan list is accessible without authentication."""
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("plans", response.data)
        self.assertEqual(len(response.data["plans"]), 2)  # Only active plans

        # Check plan data
        plan_names = [plan["name"] for plan in response.data["plans"]]
        self.assertIn("Basic Monthly", plan_names)
        self.assertIn("Premium Monthly", plan_names)
        self.assertNotIn("Yearly Premium", plan_names)  # Inactive

    def test_list_plans_gym_not_found(self):
        """Test plan list with non-existent gym."""
        non_existent_id = uuid.uuid4()
        url = reverse("gym_plans:list", kwargs={"gym_id": non_existent_id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_plans_inactive_gym(self):
        """Test plan list with inactive gym."""
        inactive_gym = Gym.objects.create(
            name="Inactive Gym",
            province="Inactive Province",
            city="Inactive City",
            address="Inactive Address",
            is_active=False,
        )
        url = reverse("gym_plans:list", kwargs={"gym_id": inactive_gym.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== CREATE TESTS ====================

    def test_create_plan_admin(self):
        """Test that admin can create a plan."""
        self.authenticate(self.admin_user)

        data = {
            "name": "New Plan",
            "description": "Brand new plan",
            "duration_months": 3,
            "visit_limit": 20,
            "price": "99.99",
            "is_active": True,
        }

        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["plan"]["name"], "New Plan")
        self.assertEqual(response.data["plan"]["price"], "99.99")

        # Verify plan was created in database
        plan = GymMembershipPlan.objects.get(gym=self.gym, name="New Plan")
        self.assertEqual(plan.duration_months, 3)
        self.assertEqual(plan.visit_limit, 20)
        self.assertTrue(plan.is_active)

    def test_create_plan_gym_owner(self):
        """Test that gym owner can create a plan."""
        self.authenticate(self.gym_owner)

        data = {
            "name": "Owner Plan",
            "description": "Created by owner",
            "duration_months": 6,
            "visit_limit": 30,
            "price": "149.99",
            "is_active": True,
        }

        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["plan"]["name"], "Owner Plan")

    def test_create_plan_regular_user_denied(self):
        """Test that regular user cannot create a plan."""
        self.authenticate(self.regular_user)

        data = {
            "name": "Hacked Plan",
            "description": "Should not be created",
            "duration_months": 1,
            "price": "0.00",
        }

        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_plan_missing_fields(self):
        """Test creating a plan with missing required fields."""
        self.authenticate(self.admin_user)

        # Missing price
        data = {
            "name": "Test Plan",
            "description": "Test Description",
            "duration_months": 1,
        }

        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_plan_gym_not_found(self):
        """Test creating a plan for non-existent gym."""
        self.authenticate(self.admin_user)

        non_existent_id = uuid.uuid4()
        url = reverse("gym_plans:create", kwargs={"gym_id": non_existent_id})

        data = {
            "name": "Test Plan",
            "description": "Test Description",
            "duration_months": 1,
            "price": "29.99",
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== UPDATE TESTS ====================

    def test_update_plan_admin(self):
        """Test that admin can update a plan."""
        self.authenticate(self.admin_user)

        url = reverse(
            "gym_plans:update",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan1.id.id,  # plan1.id is the commerce_product
            },
        )

        data = {
            "name": "Updated Plan Name",
            "price": "39.99",
        }

        response = self.client.put(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan"]["name"], "Updated Plan Name")
        self.assertEqual(response.data["plan"]["price"], "39.99")

        # Verify database update
        self.plan1.refresh_from_db()
        self.assertEqual(self.plan1.name, "Updated Plan Name")
        self.assertEqual(self.plan1.price, Decimal("39.99"))

    def test_update_plan_gym_owner(self):
        """Test that gym owner can update a plan."""
        self.authenticate(self.gym_owner)

        url = reverse(
            "gym_plans:update",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan1.id.id,
            },
        )

        data = {"description": "Updated by owner"}

        response = self.client.put(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan"]["description"], "Updated by owner")

    def test_update_plan_regular_user_denied(self):
        """Test that regular user cannot update a plan."""
        self.authenticate(self.regular_user)

        url = reverse(
            "gym_plans:update",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan1.id.id,
            },
        )

        data = {"name": "Hacked Name"}

        response = self.client.put(url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_plan_not_found(self):
        """Test updating a non-existent plan."""
        self.authenticate(self.admin_user)

        non_existent_id = uuid.uuid4()
        url = reverse(
            "gym_plans:update",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": non_existent_id,
            },
        )

        data = {"name": "New Name"}

        response = self.client.put(url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_deleted_plan(self):
        """Test updating a deleted plan (should fail)."""
        self.authenticate(self.admin_user)

        # Delete a plan
        self.plan1.soft_delete()

        url = reverse(
            "gym_plans:update",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan1.id.id,
            },
        )

        data = {"name": "Should Fail"}

        response = self.client.put(url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== DELETE TESTS ====================

    def test_delete_plan_admin(self):
        """Test that admin can delete a plan."""
        self.authenticate(self.admin_user)

        url = reverse(
            "gym_plans:delete",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan1.id.id,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify plan is soft-deleted
        self.plan1.refresh_from_db()
        self.assertTrue(self.plan1.is_deleted)
        self.assertFalse(self.plan1.is_active)

    def test_delete_plan_gym_owner(self):
        """Test that gym owner can delete a plan."""
        self.authenticate(self.gym_owner)

        url = reverse(
            "gym_plans:delete",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan2.id.id,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.plan2.refresh_from_db()
        self.assertTrue(self.plan2.is_deleted)

    def test_delete_plan_regular_user_denied(self):
        """Test that regular user cannot delete a plan."""
        self.authenticate(self.regular_user)

        url = reverse(
            "gym_plans:delete",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan1.id.id,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_plan_already_deleted(self):
        """Test deleting a plan that is already deleted."""
        self.authenticate(self.admin_user)

        # Delete plan first
        self.plan1.soft_delete()

        url = reverse(
            "gym_plans:delete",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan1.id.id,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_plan_not_found(self):
        """Test deleting a non-existent plan."""
        self.authenticate(self.admin_user)

        non_existent_id = uuid.uuid4()
        url = reverse(
            "gym_plans:delete",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": non_existent_id,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== PERMISSION TESTS ====================

    def test_unauthenticated_user_cannot_create(self):
        """Test that unauthenticated user cannot create a plan."""
        data = {
            "name": "Test Plan",
            "description": "Test",
            "duration_months": 1,
            "price": "29.99",
        }

        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_user_cannot_update(self):
        """Test that unauthenticated user cannot update a plan."""
        url = reverse(
            "gym_plans:update",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan1.id.id,
            },
        )

        response = self.client.put(url, {"name": "Hacked"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_user_cannot_delete(self):
        """Test that unauthenticated user cannot delete a plan."""
        url = reverse(
            "gym_plans:delete",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan1.id.id,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==================== DATA ISOLATION TESTS ====================

    def test_cannot_access_other_gym_plans(self):
        """Test that plans from one gym are not accessible from another gym."""
        # Create another gym
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
            is_active=True,
        )

        # Create a plan for the other gym
        other_plan = GymMembershipPlan.objects.create_plan(
            gym=other_gym,
            name="Other Gym Plan",
            description="This belongs to other gym",
            duration_months=1,
            price=Decimal("19.99"),
            is_active=True,
        )

        # Current gym's plans should not include other gym's plan
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        plan_names = [plan["name"] for plan in response.data["plans"]]
        self.assertNotIn("Other Gym Plan", plan_names)

        # Try to update other gym's plan
        self.authenticate(self.admin_user)
        url = reverse(
            "gym_plans:update",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": other_plan.id.id,
            },
        )
        response = self.client.put(url, {"name": "Hacked"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Try to delete other gym's plan
        url = reverse(
            "gym_plans:delete",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": other_plan.id.id,
            },
        )
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_plans_isolated_by_gym(self):
        """Test that plans are properly isolated by gym."""
        # Create another gym
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
            is_active=True,
        )

        # Create plan for other gym
        GymMembershipPlan.objects.create_plan(
            gym=other_gym,
            name="Other Gym Plan",
            description="Other gym description",
            duration_months=1,
            price=Decimal("19.99"),
            is_active=True,
        )

        # Get plans for first gym
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["plans"]), 2)  # Only original gym's plans

        # Get plans for other gym
        other_url = reverse("gym_plans:list", kwargs={"gym_id": other_gym.id})
        response = self.client.get(other_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["plans"]), 1)
        self.assertEqual(response.data["plans"][0]["name"], "Other Gym Plan")

    def test_list_plans_includes_gym(self):
        """Test that each plan in the list includes its gym."""
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for plan in response.data["plans"]:
            self.assertIn("gym", plan)

            self.assertEqual(plan["gym"]["id"], str(self.gym.id))
            self.assertEqual(plan["gym"]["name"], "Test Gym")
            self.assertEqual(plan["gym"]["province"], "Test Province")
            self.assertEqual(plan["gym"]["city"], "Test City")
            self.assertEqual(plan["gym"]["address"], "123 Test St")
            self.assertTrue(plan["gym"]["is_active"])

    def test_create_plan_includes_gym(self):
        """Test that the created plan response includes its gym."""
        self.authenticate(self.admin_user)

        data = {
            "name": "New Plan",
            "description": "Brand new plan",
            "duration_months": 3,
            "visit_limit": 20,
            "price": "99.99",
            "is_active": True,
        }

        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        plan_data = response.data["plan"]

        self.assertIn("gym", plan_data)
        self.assertEqual(plan_data["gym"]["id"], str(self.gym.id))
        self.assertEqual(plan_data["gym"]["name"], "Test Gym")
        self.assertEqual(plan_data["gym"]["province"], "Test Province")
        self.assertEqual(plan_data["gym"]["city"], "Test City")
        self.assertEqual(plan_data["gym"]["address"], "123 Test St")
        self.assertTrue(plan_data["gym"]["is_active"])

    def test_update_plan_includes_gym(self):
        """Test that the updated plan response includes its gym."""
        self.authenticate(self.admin_user)

        url = reverse(
            "gym_plans:update",
            kwargs={
                "gym_id": self.gym.id,
                "plan_id": self.plan1.id.id,
            },
        )

        response = self.client.put(
            url,
            {
                "name": "Updated Plan",
                "price": "39.99",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        plan_data = response.data["plan"]

        self.assertIn("gym", plan_data)
        self.assertEqual(plan_data["gym"]["id"], str(self.gym.id))
        self.assertEqual(plan_data["gym"]["name"], "Test Gym")

    def test_create_plan_cannot_set_gym_through_request(self):
        """Test that request gym data cannot override the URL gym."""
        self.authenticate(self.admin_user)

        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="456 Other St",
            is_active=True,
        )

        data = {
            "gym": str(other_gym.id),
            "name": "Test Plan",
            "description": "Test Description",
            "duration_months": 1,
            "visit_limit": 10,
            "price": "29.99",
            "is_active": True,
        }

        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        plan = GymMembershipPlan.objects.get(name="Test Plan")

        self.assertEqual(plan.gym_id, self.gym.id)
        self.assertNotEqual(plan.gym_id, other_gym.id)

        self.assertEqual(
            response.data["plan"]["gym"]["id"],
            str(self.gym.id),
        )
