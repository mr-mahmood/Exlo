# gym/tests/test_serializers.py
# type: ignore

import uuid
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from gym.models import Gym
from gym.serializers import GymSerializer
from django.conf import settings


class GymSerializerTest(TestCase):
    """Test cases for GymSerializer."""

    def setUp(self):
        settings.DEBUG = True
        self.gym_data = {
            "name": "Test Gym",
            "province": "Test Province",
            "city": "Test City",
            "address": "123 Test St",
            "latitude": "40.7128",
            "longitude": "-74.0060",
        }

    def test_serializer_valid_data(self):
        """Test serializer with valid data."""
        serializer = GymSerializer(data=self.gym_data)
        self.assertTrue(serializer.is_valid())

        gym = serializer.save()
        self.assertEqual(gym.name, "Test Gym")
        self.assertIsNotNone(gym.gym_code)

    def test_serializer_read_only_fields(self):
        """Test that read-only fields are not writable."""
        serializer = GymSerializer(
            data={
                **self.gym_data,
                "id": str(uuid.uuid7()),
                "gym_code": "CUSTOM",
                "created_at": "2024-01-01T00:00:00Z",
            }
        )
        self.assertTrue(serializer.is_valid())

        gym = serializer.save()
        self.assertNotEqual(str(gym.id), self.gym_data.get("id", ""))
        self.assertNotEqual(gym.gym_code, "CUSTOM")

    def test_serializer_photo_field(self):
        """Test that photos field is read-only."""
        gym = Gym.objects.create(**self.gym_data)
        serializer = GymSerializer(gym)

        self.assertIn("photos", serializer.data)
        self.assertEqual(serializer.data["photos"], [])
