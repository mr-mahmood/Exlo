# gym_devices/tests/test_authentication.py


import uuid
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from core.errors import APIError, GymDeviceError
from gym.models import Gym
from gym_devices.authentication import DeviceTokenAuthentication
from gym_devices.models import GymDevice


class DummyResolverMatch:
    def __init__(self, kwargs):
        self.kwargs = kwargs


class DeviceTokenAuthenticationTests(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.auth = DeviceTokenAuthentication()

        self.gym = Gym.objects.create(name="Test Gym", is_active=True)
        self.inactive_gym = Gym.objects.create(
            name="Inactive Gym",
            is_active=False,
        )
        self.other_gym = Gym.objects.create(
            name="Other Gym",
            is_active=True,
        )

        self.device, self.raw_token = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

    def _make_request(self, header_value=None, gym_id=None):
        request = self.factory.get("/")

        if header_value is not None:
            request.META["HTTP_AUTHORIZATION"] = header_value

        if gym_id is not None:
            request.resolver_match = DummyResolverMatch({"gym_id": gym_id})

        return request

    # ---------- No / Invalid header ----------

    def test_raises_when_no_authorization_header(self):
        request = self._make_request(
            header_value=None,
            gym_id=self.gym.id,
        )

        with self.assertRaises(APIError) as ctx:
            self.auth.authenticate(request)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_raises_when_wrong_keyword(self):
        request = self._make_request(
            header_value="Token abc123",
            gym_id=self.gym.id,
        )

        with self.assertRaises(APIError) as ctx:
            self.auth.authenticate(request)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_raises_when_header_has_more_than_two_parts(self):
        request = self._make_request(
            header_value="Device token extra",
            gym_id=self.gym.id,
        )

        with self.assertRaises(APIError) as ctx:
            self.auth.authenticate(request)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_raises_when_header_has_only_keyword(self):
        request = self._make_request(
            header_value="Device",
            gym_id=self.gym.id,
        )

        with self.assertRaises(APIError) as ctx:
            self.auth.authenticate(request)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_raises_when_gym_id_missing_from_resolver(self):
        request = self._make_request(
            header_value=f"Device {self.raw_token}",
            gym_id=None,
        )

        request.resolver_match = None

        with self.assertRaises(APIError) as ctx:
            self.auth.authenticate(request)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    def test_raises_when_gym_id_not_in_kwargs(self):
        request = self._make_request(
            header_value=f"Device {self.raw_token}",
            gym_id=self.gym.id,
        )

        request.resolver_match = DummyResolverMatch({})

        with self.assertRaises(APIError) as ctx:
            self.auth.authenticate(request)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.INVALID_DEVICE_CREDENTIAL[0],
        )

    # ---------- Valid token ----------

    def test_authenticates_valid_entrance_device(self):
        request = self._make_request(
            header_value=f"Device {self.raw_token}",
            gym_id=self.gym.id,
        )

        user, device = self.auth.authenticate(request)

        self.assertIsNone(user)
        self.assertEqual(device.id, self.device.id)
        self.assertEqual(
            device.device_type,
            GymDevice.GymDeviceType.ENTRANCE,
        )

    def test_authenticates_valid_locker_device(self):
        device, raw_token = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        request = self._make_request(
            header_value=f"Device {raw_token}",
            gym_id=self.gym.id,
        )

        user, authenticated_device = self.auth.authenticate(request)

        self.assertIsNone(user)
        self.assertEqual(authenticated_device.id, device.id)
        self.assertEqual(
            authenticated_device.device_type,
            GymDevice.GymDeviceType.LOCKER,
        )

    def test_keyword_is_case_insensitive(self):
        request = self._make_request(
            header_value=f"dEvIcE {self.raw_token}",
            gym_id=self.gym.id,
        )

        user, device = self.auth.authenticate(request)

        self.assertIsNone(user)
        self.assertEqual(device.id, self.device.id)

    # ---------- Invalid token ----------

    def test_raises_when_token_too_short(self):
        request = self._make_request(
            header_value="Device short",
            gym_id=self.gym.id,
        )

        with self.assertRaises(APIError) as ctx:
            self.auth.authenticate(request)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )

    def test_raises_when_token_not_matching(self):
        bad_token = self.raw_token[:12] + "0" * (len(self.raw_token) - 12)

        request = self._make_request(
            header_value=f"Device {bad_token}",
            gym_id=self.gym.id,
        )

        with self.assertRaises(APIError) as ctx:
            self.auth.authenticate(request)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )

    def test_raises_when_device_inactive(self):
        self.device.deactivate_device()

        request = self._make_request(
            header_value=f"Device {self.raw_token}",
            gym_id=self.gym.id,
        )

        with self.assertRaises(APIError) as ctx:
            self.auth.authenticate(request)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )

    def test_authenticates_when_device_active(self):
        self.device.deactivate_device()
        self.device.activate_device()

        request = self._make_request(
            header_value=f"Device {self.raw_token}",
            gym_id=self.gym.id,
        )

        result = self.auth.authenticate(request)

        self.assertIsNotNone(result)
        self.assertEqual(result[1], self.device)

    def test_raises_when_token_belongs_to_other_gym(self):
        _, other_token = GymDevice.objects.register_device(
            gym=self.other_gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        request = self._make_request(
            header_value=f"Device {other_token}",
            gym_id=self.gym.id,
        )

        with self.assertRaises(APIError) as ctx:
            self.auth.authenticate(request)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )

    # ---------- Gym errors ----------

    def test_raises_when_gym_inactive(self):
        _, token = GymDevice.objects.register_device(
            gym=self.inactive_gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        request = self._make_request(
            header_value=f"Device {token}",
            gym_id=self.inactive_gym.id,
        )

        with self.assertRaises(APIError):
            self.auth.authenticate(request)

    def test_raises_when_gym_not_found(self):
        request = self._make_request(
            header_value=f"Device {self.raw_token}",
            gym_id=uuid.uuid7(),
        )

        with self.assertRaises(APIError):
            self.auth.authenticate(request)

    # ---------- _extract_gym_id ----------

    def test_extract_gym_id_returns_none_when_no_resolver_match(self):
        request = self._make_request(header_value="Device x")

        request.resolver_match = None

        self.assertIsNone(self.auth._extract_gym_id(request))

    def test_extract_gym_id_returns_value(self):
        request = self._make_request(
            header_value="Device x",
            gym_id=self.gym.id,
        )

        self.assertEqual(
            self.auth._extract_gym_id(request),
            self.gym.id,
        )

    def test_extract_gym_id_returns_none_when_missing(self):
        request = self._make_request(header_value="Device x")

        request.resolver_match = DummyResolverMatch({})

        self.assertIsNone(self.auth._extract_gym_id(request))
