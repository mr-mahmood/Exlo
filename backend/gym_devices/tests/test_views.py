# gym_devices/tests/test_views.py


import uuid

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from core.errors import GymDeviceError
from gym.models import Gym
from gym_devices.models import GymDevice
from users.models import User


class GymDevicesViewsBaseTestCase(TestCase):
    """Base setup for gym device view tests."""

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

        self.gym = Gym.objects.create(
            name="Test Gym",
            is_active=True,
        )

        self.other_gym = Gym.objects.create(
            name="Other Gym",
            is_active=True,
        )

        self.inactive_gym = Gym.objects.create(
            name="Inactive Gym",
            is_active=False,
        )

    def _login_admin(self):
        self.client.force_authenticate(
            user=self.admin_user,
        )

    def _login_owner(self):
        self.client.force_authenticate(
            user=self.gym_owner,
        )

    def _login_regular(self):
        self.client.force_authenticate(
            user=self.regular_user,
        )


# =========================================================
# LIST VIEW
# =========================================================


class GymDevicesListAPIViewTests(GymDevicesViewsBaseTestCase):

    def _url(self, gym_id=None):
        return reverse(
            "gym_devices:list",
            kwargs={
                "gym_id": gym_id or self.gym.id,
            },
        )

    def test_list_requires_authentication(self):
        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_list_forbidden_for_regular_user(self):
        self._login_regular()

        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_list_forbidden_for_owner_non_admin(self):
        self._login_owner()

        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_list_allowed_for_admin(self):
        self._login_admin()

        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_list_returns_empty_when_no_devices(self):
        self._login_admin()

        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(response.data["devices"]),
            0,
        )

    def test_list_returns_devices_for_gym(self):
        self._login_admin()

        GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(response.data["devices"]),
            2,
        )

    def test_list_does_not_return_other_gym_devices(self):
        self._login_admin()

        GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        GymDevice.objects.register_device(
            gym=self.other_gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(response.data["devices"]),
            1,
        )

    def test_list_returns_active_and_inactive_devices(self):
        self._login_admin()

        device, _ = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        device.deactivate_device()

        GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(response.data["devices"]),
            2,
        )

    def test_list_returns_device_type(self):
        self._login_admin()

        GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        device_types = {device["device_type"] for device in response.data["devices"]}

        self.assertEqual(
            device_types,
            {
                GymDevice.GymDeviceType.ENTRANCE,
                GymDevice.GymDeviceType.LOCKER,
            },
        )

    def test_list_returns_correct_device_data(self):
        self._login_admin()

        device, _ = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        device_data = response.data["devices"][0]

        self.assertEqual(
            device_data["id"],
            str(device.id),
        )

        self.assertEqual(
            device_data["device_type"],
            GymDevice.GymDeviceType.ENTRANCE,
        )

        self.assertTrue(
            device_data["is_active"],
        )

    def test_list_returns_404_for_inactive_gym(self):
        self._login_admin()

        url = self._url(
            gym_id=self.inactive_gym.id,
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_list_returns_404_for_nonexistent_gym(self):
        self._login_admin()

        url = self._url(
            gym_id=uuid.uuid7(),
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_list_pagination_structure(self):
        self._login_admin()

        for _ in range(3):
            GymDevice.objects.register_device(
                gym=self.gym,
                device_type=GymDevice.GymDeviceType.ENTRANCE,
            )

        response = self.client.get(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "devices",
            response.data,
        )

    def test_list_does_not_expose_token(self):
        self._login_admin()

        GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        response = self.client.get(
            self._url(),
        )

        device_data = response.data["devices"][0]

        self.assertNotIn(
            "token",
            device_data,
        )

        self.assertNotIn(
            "token_hash",
            device_data,
        )

        self.assertNotIn(
            "token_prefix",
            device_data,
        )


# =========================================================
# CREATE VIEW
# =========================================================


class GymDevicesCreateAPIViewTests(GymDevicesViewsBaseTestCase):

    def _url(self, gym_id=None):
        return reverse(
            "gym_devices:create",
            kwargs={
                "gym_id": gym_id or self.gym.id,
            },
        )

    def _payload(
        self,
        device_type=GymDevice.GymDeviceType.ENTRANCE,
    ):
        return {
            "device_type": device_type,
        }

    def test_create_requires_authentication(self):
        response = self.client.post(
            self._url(),
            data=self._payload(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_create_forbidden_for_regular_user(self):
        self._login_regular()

        response = self.client.post(
            self._url(),
            data=self._payload(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_create_forbidden_for_owner_non_admin(self):
        self._login_owner()

        response = self.client.post(
            self._url(),
            data=self._payload(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_create_allowed_for_admin(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data=self._payload(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_create_entrance_device(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data=self._payload(
                GymDevice.GymDeviceType.ENTRANCE,
            ),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response.data["device"]["device_type"],
            GymDevice.GymDeviceType.ENTRANCE,
        )

        device = GymDevice.objects.get(
            id=response.data["device"]["id"],
        )

        self.assertEqual(
            device.device_type,
            GymDevice.GymDeviceType.ENTRANCE,
        )

    def test_create_locker_device(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data=self._payload(
                GymDevice.GymDeviceType.LOCKER,
            ),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response.data["device"]["device_type"],
            GymDevice.GymDeviceType.LOCKER,
        )

        device = GymDevice.objects.get(
            id=response.data["device"]["id"],
        )

        self.assertEqual(
            device.device_type,
            GymDevice.GymDeviceType.LOCKER,
        )

    def test_create_rejects_invalid_device_type(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data={
                "device_type": "invalid",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["error_code"],
            GymDeviceError.INVALID_DEVICE_TYPE[0],
        )

        self.assertEqual(
            GymDevice.objects.filter(
                gym=self.gym,
            ).count(),
            0,
        )

    def test_create_requires_device_type(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data={},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            GymDevice.objects.filter(
                gym=self.gym,
            ).count(),
            0,
        )

    def test_create_returns_device_and_token(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data=self._payload(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertIn(
            "device",
            response.data,
        )

        self.assertIn(
            "token",
            response.data,
        )

        self.assertIsInstance(
            response.data["token"],
            str,
        )

        self.assertEqual(
            len(response.data["token"]),
            64,
        )

    def test_create_persists_device(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data=self._payload(
                GymDevice.GymDeviceType.LOCKER,
            ),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        device_id = response.data["device"]["id"]

        device = GymDevice.objects.get(
            id=device_id,
        )

        self.assertEqual(
            device.gym,
            self.gym,
        )

        self.assertEqual(
            device.device_type,
            GymDevice.GymDeviceType.LOCKER,
        )

        self.assertTrue(
            device.is_active,
        )

    def test_create_token_is_hashed_in_db(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data=self._payload(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        raw_token = response.data["token"]

        device = GymDevice.objects.get(
            id=response.data["device"]["id"],
        )

        self.assertNotEqual(
            device.token_hash,
            raw_token,
        )

        self.assertEqual(
            device.token_prefix,
            raw_token[:12],
        )

    def test_create_returns_404_for_inactive_gym(self):
        self._login_admin()

        url = self._url(
            gym_id=self.inactive_gym.id,
        )

        response = self.client.post(
            url,
            data=self._payload(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_create_returns_404_for_nonexistent_gym(self):
        self._login_admin()

        url = self._url(
            gym_id=uuid.uuid7(),
        )

        response = self.client.post(
            url,
            data=self._payload(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_create_multiple_devices_for_same_gym(self):
        self._login_admin()

        response_1 = self.client.post(
            self._url(),
            data=self._payload(
                GymDevice.GymDeviceType.ENTRANCE,
            ),
        )

        response_2 = self.client.post(
            self._url(),
            data=self._payload(
                GymDevice.GymDeviceType.LOCKER,
            ),
        )

        self.assertEqual(
            response_1.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response_2.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertNotEqual(
            response_1.data["token"],
            response_2.data["token"],
        )

        self.assertNotEqual(
            response_1.data["device"]["id"],
            response_2.data["device"]["id"],
        )

    def test_create_device_response_contains_device_type(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data=self._payload(
                GymDevice.GymDeviceType.LOCKER,
            ),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response.data["device"]["device_type"],
            GymDevice.GymDeviceType.LOCKER,
        )

    def test_create_device_response_does_not_expose_hash(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data=self._payload(),
        )

        device_data = response.data["device"]

        self.assertNotIn(
            "token_hash",
            device_data,
        )

        self.assertNotIn(
            "token_prefix",
            device_data,
        )

    def test_create_token_can_authenticate_created_device(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
            data=self._payload(
                GymDevice.GymDeviceType.ENTRANCE,
            ),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        token = response.data["token"]

        device = GymDevice.objects.get(
            id=response.data["device"]["id"],
        )

        self.assertTrue(device.is_active)
        self.assertEqual(
            device.token_prefix,
            token[:12],
        )


# =========================================================
# DEACTIVATE VIEW
# =========================================================


class GymDevicesDeActiveAPIViewTests(GymDevicesViewsBaseTestCase):

    def setUp(self):
        super().setUp()

        self.device, self.raw_token = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

    def _url(self, gym_id=None, device_id=None):
        return reverse(
            "gym_devices:deactivate",
            kwargs={
                "gym_id": gym_id or self.gym.id,
                "device_id": device_id or self.device.id,
            },
        )

    def test_deactivate_requires_authentication(self):
        response = self.client.post(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_deactivate_forbidden_for_regular_user(self):
        self._login_regular()

        response = self.client.post(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_deactivate_forbidden_for_owner_non_admin(self):
        self._login_owner()

        response = self.client.post(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_deactivate_allowed_for_admin(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_deactivate_sets_device_inactive(self):
        self._login_admin()

        response = self.client.post(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.device.refresh_from_db()

        self.assertFalse(
            self.device.is_active,
        )

    def test_deactivate_does_not_change_device_type(self):
        self._login_admin()

        original_type = self.device.device_type

        response = self.client.post(
            self._url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.device.refresh_from_db()

        self.assertEqual(
            self.device.device_type,
            original_type,
        )

    def test_deactivate_returns_404_for_nonexistent_device(self):
        self._login_admin()

        url = self._url(
            device_id=uuid.uuid7(),
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_deactivate_returns_404_for_device_of_other_gym(self):
        self._login_admin()

        other_device, _ = GymDevice.objects.register_device(
            gym=self.other_gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        url = self._url(
            device_id=other_device.id,
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_deactivate_returns_404_for_inactive_gym(self):
        self._login_admin()

        url = self._url(
            gym_id=self.inactive_gym.id,
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_deactivate_already_inactive_device_returns_200(self):
        self._login_admin()
        self.device.deactivate_device()

        response = self.client.post(self._url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.device.refresh_from_db()
        self.assertFalse(self.device.is_active)

    def test_deactivate_is_idempotent(self):
        self._login_admin()

        response_1 = self.client.post(self._url())
        response_2 = self.client.post(self._url())

        self.assertEqual(response_1.status_code, status.HTTP_200_OK)
        self.assertEqual(response_2.status_code, status.HTTP_200_OK)
        self.device.refresh_from_db()
        self.assertFalse(self.device.is_active)


class GymDevicesActivateAPIViewTests(GymDevicesViewsBaseTestCase):

    def setUp(self):
        super().setUp()
        self.device, _ = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )
        self.device.deactivate_device()

    def _url(self, gym_id=None, device_id=None):
        return reverse(
            "gym_devices:activate",
            kwargs={
                "gym_id": gym_id or self.gym.id,
                "device_id": device_id or self.device.id,
            },
        )

    def test_activate_requires_authentication(self):
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_activate_forbidden_for_regular_user(self):
        self._login_regular()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_activate_forbidden_for_owner_non_admin(self):
        self._login_owner()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_activate_allowed_for_admin(self):
        self._login_admin()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.device.refresh_from_db()
        self.assertTrue(self.device.is_active)

    def test_activate_preserves_other_device_fields(self):
        self._login_admin()
        original_type = self.device.device_type
        original_hash = self.device.token_hash

        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.device.refresh_from_db()
        self.assertTrue(self.device.is_active)
        self.assertEqual(self.device.device_type, original_type)
        self.assertEqual(self.device.token_hash, original_hash)

    def test_activate_returns_404_for_nonexistent_device(self):
        self._login_admin()
        response = self.client.post(self._url(device_id=uuid.uuid7()))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_activate_returns_404_for_device_of_other_gym(self):
        self._login_admin()
        other_device, _ = GymDevice.objects.register_device(
            gym=self.other_gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )
        other_device.deactivate_device()

        response = self.client.post(self._url(device_id=other_device.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_activate_returns_404_for_inactive_gym(self):
        self._login_admin()
        response = self.client.post(self._url(gym_id=self.inactive_gym.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_activate_already_active_device_returns_200(self):
        self._login_admin()
        self.device.activate_device()

        response = self.client.post(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.device.refresh_from_db()
        self.assertTrue(self.device.is_active)

    def test_activate_is_idempotent(self):
        self._login_admin()

        response_1 = self.client.post(self._url())
        response_2 = self.client.post(self._url())

        self.assertEqual(response_1.status_code, status.HTTP_200_OK)
        self.assertEqual(response_2.status_code, status.HTTP_200_OK)
        self.device.refresh_from_db()
        self.assertTrue(self.device.is_active)
