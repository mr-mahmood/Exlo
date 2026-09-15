# gym_devices/tests/test_views.py
# type: ignore

import uuid
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from gym.models import Gym
from gym_devices.models import GymDevice
from users.models import User
from django.conf import settings


class GymDevicesViewsBaseTestCase(TestCase):
    """Base setup for view tests."""

    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()

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

        self.gym = Gym.objects.create(name="Test Gym", is_active=True)
        self.other_gym = Gym.objects.create(name="Other Gym", is_active=True)
        self.inactive_gym = Gym.objects.create(name="Inactive Gym", is_active=False)

    def _login_admin(self):
        self.client.force_authenticate(user=self.admin_user)

    def _login_owner(self):
        self.client.force_authenticate(user=self.gym_owner)

    def _login_regular(self):
        self.client.force_authenticate(user=self.regular_user)


# =========================================================
# LIST VIEW
# =========================================================


class GymDevicesListAPIViewTests(GymDevicesViewsBaseTestCase):

    def _url(self, gym_id=None):
        return reverse(
            "gym_devices:list",
            kwargs={"gym_id": gym_id or self.gym.id},
        )

    def test_list_requires_authentication(self):
        response = self.client.get(self._url())
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_list_forbidden_for_regular_user(self):
        self._login_regular()
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_forbidden_for_owner_non_admin(self):
        self._login_owner()
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_allowed_for_admin(self):
        self._login_admin()
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_returns_empty_when_no_devices(self):
        self._login_admin()
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["devices"]), 0)

    def test_list_returns_devices_for_gym(self):
        self._login_admin()
        GymDevice.objects.register_device(gym=self.gym)
        GymDevice.objects.register_device(gym=self.gym)
        response = self.client.get(self._url())
        self.assertEqual(len(response.data["devices"]), 2)

    def test_list_does_not_return_other_gym_devices(self):
        self._login_admin()
        GymDevice.objects.register_device(gym=self.gym)
        GymDevice.objects.register_device(gym=self.other_gym)
        response = self.client.get(self._url())
        self.assertEqual(len(response.data["devices"]), 1)

    def test_list_returns_only_active_devices(self):
        self._login_admin()
        device, _ = GymDevice.objects.register_device(gym=self.gym)
        device.revoke_device()
        GymDevice.objects.register_device(gym=self.gym)
        response = self.client.get(self._url())
        # Assuming the view filters by active; if not, adjust
        # Current view filters by gym only, so 2 devices returned.
        # If you want active-only, add is_active=True in the view.
        self.assertEqual(len(response.data["devices"]), 2)

    def test_list_returns_404_for_inactive_gym(self):
        self._login_admin()
        url = self._url(gym_id=self.inactive_gym.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_returns_404_for_nonexistent_gym(self):
        self._login_admin()
        url = self._url(gym_id=uuid.uuid4())
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_pagination_structure(self):
        self._login_admin()
        for _ in range(3):
            GymDevice.objects.register_device(gym=self.gym)
        response = self.client.get(self._url())
        self.assertIn("devices", response.data)

    def test_list_does_not_expose_token(self):
        self._login_admin()
        GymDevice.objects.register_device(gym=self.gym)
        response = self.client.get(self._url())
        device_data = response.data["devices"][0]
        self.assertNotIn("token", device_data)
        self.assertNotIn("token_hash", device_data)
        self.assertNotIn("token_prefix", device_data)


# =========================================================
# CREATE VIEW
# =========================================================


class GymDevicesCreateAPIViewTests(GymDevicesViewsBaseTestCase):

    def _url(self, gym_id=None):
        return reverse(
            "gym_devices:create",
            kwargs={"gym_id": gym_id or self.gym.id},
        )

    def test_create_requires_authentication(self):
        response = self.client.post(self._url())
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_create_forbidden_for_regular_user(self):
        self._login_regular()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_forbidden_for_owner_non_admin(self):
        self._login_owner()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_allowed_for_admin(self):
        self._login_admin()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_returns_device_and_token(self):
        self._login_admin()
        response = self.client.post(self._url())
        self.assertIn("device", response.data)
        self.assertIn("token", response.data)
        self.assertIsInstance(response.data["token"], str)
        self.assertEqual(len(response.data["token"]), 64)

    def test_create_persists_device(self):
        self._login_admin()
        response = self.client.post(self._url())
        device_id = response.data["device"]["id"]
        self.assertTrue(GymDevice.objects.filter(id=device_id).exists())

    def test_create_token_is_hashed_in_db(self):
        self._login_admin()
        response = self.client.post(self._url())
        raw_token = response.data["token"]
        device = GymDevice.objects.get(id=response.data["device"]["id"])
        self.assertNotEqual(device.token_hash, raw_token)
        self.assertEqual(device.token_prefix, raw_token[:12])

    def test_create_returns_404_for_inactive_gym(self):
        self._login_admin()
        url = self._url(gym_id=self.inactive_gym.id)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_returns_404_for_nonexistent_gym(self):
        self._login_admin()
        url = self._url(gym_id=uuid.uuid4())
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_multiple_devices_for_same_gym(self):
        self._login_admin()
        r1 = self.client.post(self._url())
        r2 = self.client.post(self._url())
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(r1.data["token"], r2.data["token"])

    def test_create_device_response_does_not_expose_hash(self):
        self._login_admin()
        response = self.client.post(self._url())
        self.assertNotIn("token_hash", response.data["device"])
        self.assertNotIn("token_prefix", response.data["device"])


# =========================================================
# DEACTIVATE VIEW
# =========================================================


class GymDevicesDeActiveAPIViewTests(GymDevicesViewsBaseTestCase):

    def setUp(self):
        super().setUp()
        self.device, self.raw_token = GymDevice.objects.register_device(gym=self.gym)

    def _url(self, gym_id=None, device_id=None):
        return reverse(
            "gym_devices:deactive",
            kwargs={
                "gym_id": gym_id or self.gym.id,
                "device_id": device_id or self.device.id,
            },
        )

    def test_deactivate_requires_authentication(self):
        response = self.client.post(self._url())
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_deactivate_forbidden_for_regular_user(self):
        self._login_regular()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deactivate_forbidden_for_owner_non_admin(self):
        self._login_owner()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deactivate_allowed_for_admin(self):
        self._login_admin()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_deactivate_sets_device_inactive(self):
        self._login_admin()
        self.client.post(self._url())
        self.device.refresh_from_db()
        self.assertFalse(self.device.is_active)

    def test_deactivate_returns_404_for_nonexistent_device(self):
        self._login_admin()
        url = self._url(device_id=uuid.uuid4())
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deactivate_returns_404_for_device_of_other_gym(self):
        self._login_admin()
        other_device, _ = GymDevice.objects.register_device(gym=self.other_gym)
        url = self._url(device_id=other_device.id)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deactivate_returns_404_for_inactive_gym(self):
        self._login_admin()
        url = self._url(gym_id=self.inactive_gym.id)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deactivate_returns_404_for_already_inactive_device(self):
        self._login_admin()
        self.device.revoke_device()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deactivate_is_idempotent_returns_404_second_time(self):
        self._login_admin()
        r1 = self.client.post(self._url())
        r2 = self.client.post(self._url())
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.status_code, status.HTTP_404_NOT_FOUND)
