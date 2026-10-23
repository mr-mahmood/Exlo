# gym_auth/tests/test_views.py


import uuid

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from gym.models import Gym
from gym_auth.models import UserGymRole
from users.models import User


class GymAuthViewsTest(TestCase):
    """Test cases for gym role management views."""

    def setUp(self):
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

        self.coach_user = User.objects.create_user(
            phone_number="09123334444",
            first_name="Coach",
            last_name="User",
        )

        self.staff_user = User.objects.create_user(
            phone_number="09125556666",
            first_name="Staff",
            last_name="User",
        )

        # Create gyms
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
            is_active=True,
        )

        self.other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="456 Other St",
            is_active=True,
        )

        # Assign gym owner
        self.owner_role = UserGymRole.objects.create_owner(
            user=self.gym_owner,
            gym=self.gym,
        )

        # Existing coach and staff roles
        self.coach_role = UserGymRole.objects.create_coach(
            user=self.coach_user,
            gym=self.gym,
        )

        self.staff_role = UserGymRole.objects.create_staff(
            user=self.staff_user,
            gym=self.gym,
        )

        # URLs
        self.list_url = reverse(
            "gym_auth:gym-roles-list",
            kwargs={"gym_id": self.gym.id},
        )

        self.owner_create_url = reverse(
            "gym_auth:gym-owner-create",
            kwargs={"gym_id": self.gym.id},
        )

        self.coach_create_url = reverse(
            "gym_auth:gym-coach-create",
            kwargs={"gym_id": self.gym.id},
        )

        self.staff_create_url = reverse(
            "gym_auth:gym-staff-create",
            kwargs={"gym_id": self.gym.id},
        )

    def authenticate(self, user):
        """Authenticate a user for API requests."""
        self.client.force_authenticate(user=user)

    def role_delete_url(self, gym_id, role_id):
        return reverse(
            "gym_auth:gym-role-delete",
            kwargs={
                "gym_id": gym_id,
                "role_id": role_id,
            },
        )

    def staff_role_delete_url(self, gym_id, role_id):
        return reverse(
            "gym_auth:gym-staff-role-delete",
            kwargs={
                "gym_id": gym_id,
                "role_id": role_id,
            },
        )

    # ==================== LIST TESTS ====================

    def test_list_roles_admin(self):
        """Test that admin can list gym role assignments."""
        self.authenticate(self.admin_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("users", response.data)

        role_ids = {role["id"] for role in response.data["users"]}

        self.assertIn(str(self.owner_role.id), role_ids)
        self.assertIn(str(self.coach_role.id), role_ids)
        self.assertIn(str(self.staff_role.id), role_ids)

    def test_list_roles_gym_owner(self):
        """Test that the gym owner can list role assignments."""
        self.authenticate(self.gym_owner)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("users", response.data)

    def test_list_roles_regular_user_denied(self):
        """Test that a regular user cannot list role assignments."""
        self.authenticate(self.regular_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_roles_unauthenticated(self):
        """Test that an unauthenticated user cannot list role assignments."""
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_roles_gym_not_found(self):
        """Test listing roles for a non-existent gym."""
        self.authenticate(self.admin_user)

        url = reverse(
            "gym_auth:gym-roles-list",
            kwargs={"gym_id": uuid.uuid7()},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_roles_isolated_by_gym(self):
        """Test that each gym returns only its own role assignments."""
        self.authenticate(self.admin_user)

        other_role = UserGymRole.objects.create_staff(
            user=self.regular_user,
            gym=self.other_gym,
        )

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        role_ids = {role["id"] for role in response.data["users"]}

        self.assertNotIn(str(other_role.id), role_ids)

    def test_list_roles_query_count_does_not_grow_with_role_count(self):
        """Ensure listing roles does not produce N+1 queries."""
        self.authenticate(self.admin_user)

        # Measure the query count with the existing three roles.
        with self.assertNumQueries(3):
            response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Add more roles with distinct users.
        for i in range(10):
            user = User.objects.create_user(
                phone_number=f"0912000{i:04d}",
                first_name=f"User{i}",
                last_name="Test",
            )
            UserGymRole.objects.create_staff(
                user=user,
                gym=self.gym,
            )

        # The query count should remain constant.
        with self.assertNumQueries(3):
            response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==================== OWNER CREATE TESTS ====================

    def test_create_owner_admin(self):
        """Test that an admin can assign an owner."""
        self.authenticate(self.admin_user)

        data = {"user": str(self.regular_user.id)}

        response = self.client.post(self.owner_create_url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(
            UserGymRole.objects.filter(
                user=self.regular_user,
                gym=self.gym,
                role=UserGymRole.Role.OWNER,
            ).exists()
        )

    def test_create_owner_gym_owner_denied(self):
        """Test that a gym owner cannot assign another owner."""
        self.authenticate(self.gym_owner)

        response = self.client.post(
            self.owner_create_url,
            {"user": str(self.regular_user.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertFalse(
            UserGymRole.objects.filter(
                user=self.regular_user,
                gym=self.gym,
                role=UserGymRole.Role.OWNER,
            ).exists()
        )

    def test_create_owner_regular_user_denied(self):
        """Test that a regular user cannot assign an owner."""
        self.authenticate(self.regular_user)

        response = self.client.post(
            self.owner_create_url,
            {"user": str(self.coach_user.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_owner_unauthenticated(self):
        """Test that an unauthenticated user cannot assign an owner."""
        response = self.client.post(
            self.owner_create_url,
            {"user": str(self.regular_user.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==================== COACH CREATE TESTS ====================

    def test_create_coach_admin(self):
        """Test that an admin can assign a coach."""
        self.authenticate(self.admin_user)

        response = self.client.post(
            self.coach_create_url,
            {"user": str(self.regular_user.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(
            UserGymRole.objects.filter(
                user=self.regular_user,
                gym=self.gym,
                role=UserGymRole.Role.COACH,
            ).exists()
        )

    def test_create_coach_gym_owner(self):
        """Test that a gym owner can assign a coach."""
        self.authenticate(self.gym_owner)

        response = self.client.post(
            self.coach_create_url,
            {"user": str(self.regular_user.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(
            UserGymRole.objects.filter(
                user=self.regular_user,
                gym=self.gym,
                role=UserGymRole.Role.COACH,
            ).exists()
        )

    def test_create_coach_regular_user_denied(self):
        """Test that a regular user cannot assign a coach."""
        self.authenticate(self.regular_user)

        response = self.client.post(
            self.coach_create_url,
            {"user": str(self.staff_user.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== STAFF CREATE TESTS ====================

    def test_create_staff_admin(self):
        """Test that an admin can assign staff."""
        self.authenticate(self.admin_user)

        response = self.client.post(
            self.staff_create_url,
            {"user": str(self.regular_user.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(
            UserGymRole.objects.filter(
                user=self.regular_user,
                gym=self.gym,
                role=UserGymRole.Role.STAFF,
            ).exists()
        )

    def test_create_staff_gym_owner(self):
        """Test that a gym owner can assign staff."""
        self.authenticate(self.gym_owner)

        response = self.client.post(
            self.staff_create_url,
            {"user": str(self.regular_user.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(
            UserGymRole.objects.filter(
                user=self.regular_user,
                gym=self.gym,
                role=UserGymRole.Role.STAFF,
            ).exists()
        )

    def test_create_staff_regular_user_denied(self):
        """Test that a regular user cannot assign staff."""
        self.authenticate(self.regular_user)

        response = self.client.post(
            self.staff_create_url,
            {"user": str(self.coach_user.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== ADMIN ROLE DELETE TESTS ====================

    def test_admin_delete_owner_role(self):
        """Test that admin can delete an owner assignment."""
        self.authenticate(self.admin_user)

        url = self.role_delete_url(
            self.gym.id,
            self.owner_role.id,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(
            UserGymRole.objects.filter(
                id=self.owner_role.id,
            ).exists()
        )

    def test_admin_delete_coach_role(self):
        """Test that admin can delete a coach assignment."""
        self.authenticate(self.admin_user)

        url = self.role_delete_url(
            self.gym.id,
            self.coach_role.id,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(
            UserGymRole.objects.filter(
                id=self.coach_role.id,
            ).exists()
        )

    def test_admin_delete_staff_role(self):
        """Test that admin can delete a staff assignment."""
        self.authenticate(self.admin_user)

        url = self.role_delete_url(
            self.gym.id,
            self.staff_role.id,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(
            UserGymRole.objects.filter(
                id=self.staff_role.id,
            ).exists()
        )

    def test_admin_delete_role_not_found(self):
        """Test deleting a non-existent role assignment."""
        self.authenticate(self.admin_user)

        url = self.role_delete_url(
            self.gym.id,
            uuid.uuid7(),
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_cannot_delete_role_from_another_gym(self):
        """Test that the role ID must belong to the URL gym."""
        self.authenticate(self.admin_user)

        other_role = UserGymRole.objects.create_staff(
            user=self.regular_user,
            gym=self.other_gym,
        )

        url = self.role_delete_url(
            self.gym.id,
            other_role.id,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertTrue(UserGymRole.objects.filter(id=other_role.id).exists())

    # ==================== OWNER ROLE DELETE TESTS ====================

    def test_owner_delete_coach_role(self):
        """Test that the gym owner can delete a coach assignment."""
        self.authenticate(self.gym_owner)

        url = self.staff_role_delete_url(
            self.gym.id,
            self.coach_role.id,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(
            UserGymRole.objects.filter(
                id=self.coach_role.id,
            ).exists()
        )

    def test_owner_delete_staff_role(self):
        """Test that the gym owner can delete a staff assignment."""
        self.authenticate(self.gym_owner)

        url = self.staff_role_delete_url(
            self.gym.id,
            self.staff_role.id,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(
            UserGymRole.objects.filter(
                id=self.staff_role.id,
            ).exists()
        )

    def test_owner_cannot_delete_owner_role(self):
        """Test that the owner endpoint cannot delete an owner."""
        self.authenticate(self.gym_owner)

        url = self.staff_role_delete_url(
            self.gym.id,
            self.owner_role.id,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertTrue(
            UserGymRole.objects.filter(
                id=self.owner_role.id,
            ).exists()
        )

    def test_regular_user_cannot_delete_coach_role(self):
        """Test that a regular user cannot delete a coach assignment."""
        self.authenticate(self.regular_user)

        url = self.staff_role_delete_url(
            self.gym.id,
            self.coach_role.id,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertTrue(
            UserGymRole.objects.filter(
                id=self.coach_role.id,
            ).exists()
        )

    def test_owner_cannot_delete_role_from_another_gym(self):
        """Test that an owner cannot delete another gym's role."""
        self.authenticate(self.gym_owner)

        other_role = UserGymRole.objects.create_staff(
            user=self.regular_user,
            gym=self.other_gym,
        )

        url = self.staff_role_delete_url(
            self.gym.id,
            other_role.id,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertTrue(UserGymRole.objects.filter(id=other_role.id).exists())

    def test_owner_delete_role_not_found(self):
        """Test deleting a non-existent coach or staff assignment."""
        self.authenticate(self.gym_owner)

        url = self.staff_role_delete_url(
            self.gym.id,
            uuid.uuid7(),
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== UNAUTHENTICATED DELETE TESTS ====================

    def test_unauthenticated_user_cannot_delete_any_role(self):
        """Test that unauthenticated users cannot delete role assignments."""
        admin_delete_url = self.role_delete_url(
            self.gym.id,
            self.coach_role.id,
        )

        response = self.client.delete(admin_delete_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertTrue(
            UserGymRole.objects.filter(
                id=self.coach_role.id,
            ).exists()
        )

    def test_unauthenticated_user_cannot_delete_staff_role(self):
        """Test that unauthenticated users cannot use the owner endpoint."""
        url = self.staff_role_delete_url(
            self.gym.id,
            self.staff_role.id,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertTrue(
            UserGymRole.objects.filter(
                id=self.staff_role.id,
            ).exists()
        )
