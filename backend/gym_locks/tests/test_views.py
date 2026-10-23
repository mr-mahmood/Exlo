# gym_locks/tests/test_views.py


import uuid

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from gym.models import Gym
from gym_auth.models import UserGymRole
from gym_locks.models import GymLocker
from users.models import User


class GymLockerViewsTest(TestCase):
    """Tests for gym locker API views."""

    def setUp(self):
        self.client = APIClient()

        self.admin_user = User.objects.create_superuser(
            phone_number="09121234567",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
        )

        self.owner_user = User.objects.create_user(
            phone_number="09129876543",
            first_name="Owner",
            last_name="User",
        )

        self.staff_user = User.objects.create_user(
            phone_number="09121112222",
            first_name="Staff",
            last_name="User",
        )

        self.regular_user = User.objects.create_user(
            phone_number="09123334444",
            first_name="Regular",
            last_name="User",
        )

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

        UserGymRole.objects.create_owner(
            user=self.owner_user,
            gym=self.gym,
        )

        UserGymRole.objects.create_staff(
            user=self.staff_user,
            gym=self.gym,
        )

        self.locker = GymLocker.objects.create(
            gym=self.gym,
            number=1,
        )

        self.other_locker = GymLocker.objects.create(
            gym=self.other_gym,
            number=1,
        )

        self.list_url = reverse(
            "gym_locks:gym_locks-list",
            kwargs={"gym_id": self.gym.id},
        )

        self.create_url = reverse(
            "gym_locks:gym_locks-create",
            kwargs={"gym_id": self.gym.id},
        )

        self.activate_url = reverse(
            "gym_locks:gym_locks-activate",
            kwargs={
                "gym_id": self.gym.id,
                "locker_id": self.locker.id,
            },
        )

        self.deactivate_url = reverse(
            "gym_locks:gym_locks-deactivate",
            kwargs={
                "gym_id": self.gym.id,
                "locker_id": self.locker.id,
            },
        )

        self.manual_open_url = reverse(
            "gym_locks:gym_locks-open-manual",
            kwargs={"gym_id": self.gym.id},
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    # ==================== LIST TESTS ====================

    def test_list_lockers_admin(self):
        self.authenticate(self.admin_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("lockers", response.data)

        locker_ids = {locker["id"] for locker in response.data["lockers"]}

        self.assertIn(str(self.locker.id), locker_ids)
        self.assertNotIn(str(self.other_locker.id), locker_ids)

    def test_list_lockers_gym_staff(self):
        self.authenticate(self.staff_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("lockers", response.data)

    def test_list_lockers_gym_owner(self):
        self.authenticate(self.owner_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_lockers_regular_user_denied(self):
        self.authenticate(self.regular_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_lockers_unauthenticated(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_list_lockers_gym_not_found(self):
        self.authenticate(self.admin_user)

        url = reverse(
            "gym_locks:gym_locks-list",
            kwargs={"gym_id": uuid.uuid7()},
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    # ==================== CREATE TESTS ====================

    def test_create_lockers_admin(self):
        self.authenticate(self.admin_user)

        response = self.client.post(
            self.create_url,
            {"count": 3},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            GymLocker.objects.filter(gym=self.gym).count(),
            4,  # One existing locker + three new lockers.
        )

        self.assertEqual(
            list(
                GymLocker.objects.filter(gym=self.gym)
                .order_by("number")
                .values_list("number", flat=True)
            ),
            [1, 2, 3, 4],
        )

    def test_create_lockers_owner_denied(self):
        self.authenticate(self.owner_user)

        response = self.client.post(
            self.create_url,
            {"count": 3},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.assertEqual(
            GymLocker.objects.filter(gym=self.gym).count(),
            1,
        )

    def test_create_lockers_staff_denied(self):
        self.authenticate(self.staff_user)

        response = self.client.post(
            self.create_url,
            {"count": 3},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.assertEqual(
            GymLocker.objects.filter(gym=self.gym).count(),
            1,
        )

    def test_create_lockers_unauthenticated(self):
        response = self.client.post(
            self.create_url,
            {"count": 3},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    # ==================== ACTIVATE TESTS ====================

    def test_activate_inactive_locker(self):
        self.authenticate(self.staff_user)

        self.locker.deactivate()

        response = self.client.post(self.activate_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.locker.refresh_from_db()
        self.assertTrue(self.locker.is_active)

    def test_activate_already_active_locker(self):
        self.authenticate(self.staff_user)

        response = self.client.post(self.activate_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.locker.refresh_from_db()
        self.assertTrue(self.locker.is_active)

    def test_activate_locker_from_another_gym_denied(self):
        self.authenticate(self.staff_user)

        url = reverse(
            "gym_locks:gym_locks-activate",
            kwargs={
                "gym_id": self.gym.id,
                "locker_id": self.other_locker.id,
            },
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.other_locker.refresh_from_db()
        self.assertTrue(self.other_locker.is_active)

    def test_activate_locker_regular_user_denied(self):
        self.authenticate(self.regular_user)

        response = self.client.post(self.activate_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    # ==================== DEACTIVATE TESTS ====================

    def test_deactivate_active_locker(self):
        self.authenticate(self.staff_user)

        response = self.client.post(self.deactivate_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.locker.refresh_from_db()
        self.assertFalse(self.locker.is_active)

    def test_deactivate_already_inactive_locker(self):
        self.authenticate(self.staff_user)

        self.locker.deactivate()

        response = self.client.post(self.deactivate_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.locker.refresh_from_db()
        self.assertFalse(self.locker.is_active)

    def test_deactivate_locker_from_another_gym_denied(self):
        self.authenticate(self.staff_user)

        url = reverse(
            "gym_locks:gym_locks-deactivate",
            kwargs={
                "gym_id": self.gym.id,
                "locker_id": self.other_locker.id,
            },
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.other_locker.refresh_from_db()
        self.assertTrue(self.other_locker.is_active)

    def test_deactivate_locker_regular_user_denied(self):
        self.authenticate(self.regular_user)

        response = self.client.post(self.deactivate_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.locker.refresh_from_db()
        self.assertTrue(self.locker.is_active)

    # ==================== MANUAL OPEN TESTS ====================

    def test_manual_open_returns_assigned_locker_number(self):
        self.authenticate(self.staff_user)

        self.locker.assigned_user = self.regular_user
        self.locker.save(update_fields=["assigned_user"])

        response = self.client.post(
            self.manual_open_url,
            {"phone_number": self.regular_user.phone_number},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data,
            {"locker_number": self.locker.number},
        )

    def test_manual_open_unassigned_user_fails(self):
        self.authenticate(self.staff_user)

        response = self.client.post(
            self.manual_open_url,
            {"phone_number": self.regular_user.phone_number},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_manual_open_regular_user_denied(self):
        self.authenticate(self.regular_user)

        response = self.client.post(
            self.manual_open_url,
            {"phone_number": self.regular_user.phone_number},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
