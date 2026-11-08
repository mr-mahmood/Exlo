# gym/tests/test_views.py


import uuid
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch
from users.models import User
from gym.models import Gym
from gym_auth.models import UserGymRole
from django.conf import settings
from django.core.cache import cache


class GymViewsTest(TestCase):
    """Test cases for Gym views (CRUD operations)."""

    def setUp(self):
        cache.clear()
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

        # Create gym with all required fields
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
        )

        # Make gym_owner the owner of the gym
        UserGymRole.objects.create(user=self.gym_owner, gym=self.gym, role=UserGymRole.Role.OWNER)

    def authenticate(self, user):
        """Helper to authenticate a user."""
        self.client.force_authenticate(user=user)

    # ==================== GYM LIST TESTS ====================

    def test_gym_list_public_access(self):
        """Test that gym list is accessible without authentication."""
        response = self.client.get(reverse("gym:list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("gyms", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)

    def test_gym_list_returns_only_active_gyms(self):
        """Test that gym list returns only active gyms."""
        inactive_gym = Gym.objects.create(
            name="Inactive Gym",
            province="Inactive Province",
            city="Inactive City",
            address="Inactive Address",
            is_active=False,
        )

        response = self.client.get(reverse("gym:list"))
        gym_ids = [gym["id"] for gym in response.data["gyms"]]

        self.assertIn(str(self.gym.id), gym_ids)
        self.assertNotIn(str(inactive_gym.id), gym_ids)

    # ==================== GYM DETAIL TESTS ====================

    def test_gym_detail_public_access(self):
        """Test that gym detail is accessible without authentication."""
        response = self.client.get(reverse("gym:detail", kwargs={"gym_id": self.gym.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["id"], str(self.gym.id))
        self.assertEqual(response.data["gym"]["name"], "Test Gym")

    def test_gym_detail_not_found(self):
        """Test gym detail with non-existent gym ID."""
        non_existent_id = uuid.uuid7()
        response = self.client.get(reverse("gym:detail", kwargs={"gym_id": non_existent_id}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_detail_inactive_gym(self):
        """Test that inactive gym returns 404."""
        inactive_gym = Gym.objects.create(
            name="Inactive Gym",
            province="Inactive Province",
            city="Inactive City",
            address="Inactive Address",
            is_active=False,
        )
        response = self.client.get(reverse("gym:detail", kwargs={"gym_id": inactive_gym.id}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== GYM CREATE TESTS ====================

    def test_gym_create_admin_only(self):
        """Test that only admin can create gym."""
        data = {
            "name": "New Gym",
            "province": "New Province",
            "city": "New City",
            "address": "456 New St",
        }

        self.authenticate(self.regular_user)
        response = self.client.post(reverse("gym:create"), data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.authenticate(self.gym_owner)
        response = self.client.post(reverse("gym:create"), data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.authenticate(self.admin_user)
        response = self.client.post(reverse("gym:create"), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["gym"]["name"], "New Gym")

    def test_gym_create_missing_required_fields(self):
        """Test gym creation with missing required fields."""
        self.authenticate(self.admin_user)

        # Missing name
        data = {"province": "New Province", "city": "New City", "address": "456 New St"}
        response = self.client.post(reverse("gym:create"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Missing province
        data = {"name": "New Gym", "city": "New City", "address": "456 New St"}
        response = self.client.post(reverse("gym:create"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==================== GYM UPDATE TESTS ====================

    def test_gym_update_admin_or_owner_only(self):
        """Test that only admin or gym owner can update gym."""
        data = {"name": "Updated Gym Name"}

        self.authenticate(self.regular_user)
        response = self.client.put(reverse("gym:update", kwargs={"gym_id": self.gym.id}), data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.authenticate(self.gym_owner)
        response = self.client.put(reverse("gym:update", kwargs={"gym_id": self.gym.id}), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["name"], "Updated Gym Name")

    def test_gym_update_owner_of_other_gym(self):
        """Test that owner of one gym cannot update another gym."""
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
        )

        data = {"name": "Hacked Gym Name"}
        self.authenticate(self.gym_owner)
        response = self.client.put(reverse("gym:update", kwargs={"gym_id": other_gym.id}), data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_update_partial(self):
        """Test partial update of gym."""
        self.authenticate(self.admin_user)

        data = {"city": "New City"}
        response = self.client.put(reverse("gym:update", kwargs={"gym_id": self.gym.id}), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["city"], "New City")

    def test_gym_update_cannot_change_active_state(self):
        for user in (self.admin_user, self.gym_owner):
            for active in (True, False):
                with self.subTest(user=user.phone_number, is_active=active):
                    Gym.objects.filter(pk=self.gym.pk).update(is_active=active)
                    self.authenticate(user)
                    response = self.client.put(
                        reverse("gym:update", kwargs={"gym_id": self.gym.id}),
                        {"city": "Updated City", "is_active": not active},
                        format="json",
                    )
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    self.gym.refresh_from_db()
                    self.assertEqual(self.gym.city, "Updated City")
                    self.assertEqual(self.gym.is_active, active)
                    self.assertEqual(response.data["gym"]["is_active"], active)

    # ==================== GYM ACTIVATION TESTS ====================

    def test_gym_activation_endpoints_deny_non_admins(self):
        for user in (self.gym_owner, self.regular_user):
            for action, method, active in (
                ("delete", "delete", True),
                ("restore", "post", False),
            ):
                with self.subTest(user=user, action=action):
                    Gym.objects.filter(pk=self.gym.pk).update(is_active=active)
                    self.authenticate(user)
                    response = getattr(self.client, method)(reverse(f"gym:{action}", kwargs={"gym_id": self.gym.id}))
                    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                    self.gym.refresh_from_db()
                    self.assertEqual(self.gym.is_active, active)

    def test_admin_can_deactivate_and_restore_gym(self):
        self.authenticate(self.admin_user)
        for action, method, expected_active in (
            ("delete", "delete", False),
            ("restore", "post", True),
        ):
            for attempt in range(2):
                with self.subTest(action=action, attempt=attempt):
                    response = getattr(self.client, method)(reverse(f"gym:{action}", kwargs={"gym_id": self.gym.id}))
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    self.gym.refresh_from_db()
                    self.assertEqual(self.gym.is_active, expected_active)

    def test_admin_activation_endpoints_missing_gym(self):
        self.authenticate(self.admin_user)
        missing_id = uuid.uuid7()
        for action, method in (("delete", "delete"), ("restore", "post")):
            with self.subTest(action=action):
                response = getattr(self.client, method)(reverse(f"gym:{action}", kwargs={"gym_id": missing_id}))
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_activation_updates_public_visibility(self):
        detail_url = reverse("gym:detail", kwargs={"gym_id": self.gym.id})
        self.assertEqual(self.client.get(detail_url).status_code, status.HTTP_200_OK)
        response = self.client.get(reverse("gym:list"))
        self.assertIn(str(self.gym.id), [gym["id"] for gym in response.data["gyms"]])

        for action, method, expected_active in (
            ("delete", "delete", False),
            ("restore", "post", True),
        ):
            with self.subTest(action=action):
                self.authenticate(self.admin_user)
                with self.captureOnCommitCallbacks(execute=True):
                    response = getattr(self.client, method)(reverse(f"gym:{action}", kwargs={"gym_id": self.gym.id}))
                self.assertEqual(response.status_code, status.HTTP_200_OK)

                self.authenticate(None)
                response = self.client.get(detail_url)
                expected_status = status.HTTP_200_OK if expected_active else status.HTTP_404_NOT_FOUND
                self.assertEqual(response.status_code, expected_status)
                response = self.client.get(reverse("gym:list"))
                gym_ids = [gym["id"] for gym in response.data["gyms"]]
                self.assertEqual(str(self.gym.id) in gym_ids, expected_active)

    # ==================== PERMISSION TESTS ====================

    def test_is_gym_owner_permission(self):
        """Test that IsGymOwner permission works correctly."""
        self.authenticate(self.gym_owner)
        response = self.client.get(reverse("gym:detail", kwargs={"gym_id": self.gym.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.authenticate(self.regular_user)
        response = self.client.put(reverse("gym:update", kwargs={"gym_id": self.gym.id}), {"name": "Hacked"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_has_access_to_all_gyms(self):
        """Test that admin can access and manage any gym."""
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
        )

        self.authenticate(self.admin_user)

        response = self.client.get(reverse("gym:detail", kwargs={"gym_id": other_gym.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.put(
            reverse("gym:update", kwargs={"gym_id": other_gym.id}),
            {"name": "Updated By Admin"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
