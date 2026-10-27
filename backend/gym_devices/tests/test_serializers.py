# gym_devices/tests/test_serializer.py


from django.test import TestCase
from core.errors import APIError, GymDeviceError
from gym.models import Gym
from gym_devices.models import GymDevice
from gym_devices.serializers import GymDeviceSerializer


class GymDeviceSerializerTests(TestCase):

    def setUp(self):
        self.gym = Gym.objects.create(
            name="Test Gym",
            is_active=True,
        )

        self.device, self.raw_token = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

    def test_serializer_contains_expected_fields(self):
        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        data = serializer.data

        expected = {
            "id",
            "gym",
            "device_type",
            "is_active",
            "created_at",
            "updated_at",
        }

        self.assertEqual(
            set(data.keys()),
            expected,
        )

    def test_serializer_returns_entrance_device_type(self):
        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        self.assertEqual(
            serializer.data["device_type"],
            GymDevice.GymDeviceType.ENTRANCE,
        )

    def test_serializer_returns_locker_device_type(self):
        self.device.device_type = GymDevice.GymDeviceType.LOCKER
        self.device.save(update_fields=["device_type"])

        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        self.assertEqual(
            serializer.data["device_type"],
            GymDevice.GymDeviceType.LOCKER,
        )

    def test_serializer_does_not_expose_token_hash(self):
        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        self.assertNotIn(
            "token_hash",
            serializer.data,
        )
        self.assertNotIn(
            "token_prefix",
            serializer.data,
        )

    def test_serializer_does_not_expose_raw_token(self):
        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        self.assertNotIn(
            "token",
            serializer.data,
        )

    def test_id_is_serialized_as_string(self):
        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        self.assertEqual(
            serializer.data["id"],
            str(self.device.id),
        )

    def test_gym_is_nested_basic_serializer(self):
        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        self.assertIn(
            "gym",
            serializer.data,
        )
        self.assertIsInstance(
            serializer.data["gym"],
            dict,
        )
        self.assertEqual(
            serializer.data["gym"]["id"],
            str(self.gym.id),
        )

    def test_is_active_default_true(self):
        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        self.assertTrue(serializer.data["is_active"])

    def test_is_active_false_after_deactivate(self):
        self.device.deactivate_device()
        self.device.refresh_from_db()

        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        self.assertFalse(serializer.data["is_active"])

    def test_is_active_true_after_activate(self):
        self.device.deactivate_device()
        self.device.activate_device()
        self.device.refresh_from_db()

        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        self.assertTrue(serializer.data["is_active"])

    def test_created_at_and_updated_at_are_present(self):
        serializer = GymDeviceSerializer(
            instance=self.device,
        )

        self.assertIsNotNone(serializer.data["created_at"])
        self.assertIsNotNone(serializer.data["updated_at"])

    def test_invalid_device_type_raises_custom_api_error(self):
        serializer = GymDeviceSerializer(
            data={
                "device_type": "invalid",
            }
        )

        with self.assertRaises(APIError) as ctx:
            serializer.is_valid(raise_exception=True)

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.INVALID_DEVICE_TYPE[0],
        )

    def test_entrance_device_type_is_valid(self):
        serializer = GymDeviceSerializer(
            data={
                "device_type": GymDevice.GymDeviceType.ENTRANCE,
            }
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

    def test_locker_device_type_is_valid(self):
        serializer = GymDeviceSerializer(
            data={
                "device_type": GymDevice.GymDeviceType.LOCKER,
            }
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

    def test_missing_device_type_is_invalid(self):
        serializer = GymDeviceSerializer(data={})

        self.assertFalse(serializer.is_valid())

        self.assertIn(
            "device_type",
            serializer.errors,
        )

    def test_device_type_is_writable_for_creation(self):
        serializer = GymDeviceSerializer(
            data={
                "device_type": GymDevice.GymDeviceType.LOCKER,
            }
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        self.assertEqual(
            serializer.validated_data["device_type"],
            GymDevice.GymDeviceType.LOCKER,
        )

    def test_read_only_fields_are_not_writable(self):
        serializer = GymDeviceSerializer(
            instance=self.device,
            data={
                "id": str(self.device.id),
                "gym": str(self.gym.id),
                "is_active": False,
                "created_at": "2020-01-01T00:00:00Z",
                "updated_at": "2020-01-01T00:00:00Z",
                "token_hash": "hack",
                "token_prefix": "hack",
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        self.assertNotIn(
            "is_active",
            serializer.validated_data,
        )
        self.assertNotIn(
            "token_hash",
            serializer.validated_data,
        )

    def test_serialize_multiple_devices(self):
        device2, _ = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        serializer = GymDeviceSerializer(
            instance=[self.device, device2],
            many=True,
        )

        self.assertEqual(
            len(serializer.data),
            2,
        )

    def test_serializer_with_request_context(self):
        class DummyRequest:
            pass

        serializer = GymDeviceSerializer(
            instance=self.device,
            context={
                "request": DummyRequest(),
            },
        )

        self.assertIn(
            "id",
            serializer.data,
        )
