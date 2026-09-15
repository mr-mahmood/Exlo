# gym_devices/tests/test_serializer.py
# type: ignore

from django.conf import settings
from django.test import TestCase
from gym.models import Gym
from gym_devices.models import GymDevice
from gym_devices.serializers import GymDeviceSerializer


class GymDeviceSerializerTests(TestCase):
    """Tests for GymDeviceSerializer."""

    def setUp(self):
        settings.DEBUG = True
        self.gym = Gym.objects.create(name="Test Gym", is_active=True)
        self.device, self.raw_token = GymDevice.objects.register_device(gym=self.gym)

    def test_serializer_contains_expected_fields(self):
        serializer = GymDeviceSerializer(instance=self.device)
        data = serializer.data
        expected = {
            "id",
            "gym",
            "is_active",
            "created_at",
            "updated_at",
        }
        self.assertEqual(set(data.keys()), expected)

    def test_serializer_does_not_expose_token_hash(self):
        serializer = GymDeviceSerializer(instance=self.device)
        self.assertNotIn("token_hash", serializer.data)
        self.assertNotIn("token_prefix", serializer.data)

    def test_serializer_does_not_expose_raw_token(self):
        serializer = GymDeviceSerializer(instance=self.device)
        self.assertNotIn("token", serializer.data)

    def test_id_is_serialized_as_string(self):
        serializer = GymDeviceSerializer(instance=self.device)
        self.assertEqual(serializer.data["id"], str(self.device.id))

    def test_gym_is_nested_basic_serializer(self):
        serializer = GymDeviceSerializer(instance=self.device)
        self.assertIn("gym", serializer.data)
        self.assertIsInstance(serializer.data["gym"], dict)
        self.assertEqual(serializer.data["gym"]["id"], str(self.gym.id))

    def test_is_active_default_true(self):
        serializer = GymDeviceSerializer(instance=self.device)
        self.assertTrue(serializer.data["is_active"])

    def test_is_active_false_after_revoke(self):
        self.device.revoke_device()
        self.device.refresh_from_db()
        serializer = GymDeviceSerializer(instance=self.device)
        self.assertFalse(serializer.data["is_active"])

    def test_created_at_and_updated_at_are_present(self):
        serializer = GymDeviceSerializer(instance=self.device)
        self.assertIsNotNone(serializer.data["created_at"])
        self.assertIsNotNone(serializer.data["updated_at"])

    def test_all_fields_are_read_only(self):
        serializer = GymDeviceSerializer(
            instance=self.device,
            data={"is_active": False, "token_hash": "hack"},
        )
        self.assertTrue(serializer.is_valid())
        # Read-only fields should not be modified
        self.assertTrue(serializer.validated_data == {})

    def test_serialize_multiple_devices(self):
        device2, _ = GymDevice.objects.register_device(gym=self.gym)
        serializer = GymDeviceSerializer(instance=[self.device, device2], many=True)
        self.assertEqual(len(serializer.data), 2)

    def test_serializer_with_request_context(self):
        class DummyRequest:
            pass

        serializer = GymDeviceSerializer(
            instance=self.device,
            context={"request": DummyRequest()},
        )
        self.assertIn("id", serializer.data)
