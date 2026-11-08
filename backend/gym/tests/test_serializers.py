# gym/tests/test_serializers.py


import uuid
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from gym.models import Gym
from gym.serializers import GymSerializer
from django.conf import settings


class GymSerializerTest(TestCase):
    """Test cases for GymSerializer."""

    def setUp(self):
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

    def test_serializer_photo_field(self):
        """Test that photos field is read-only."""
        gym = Gym.objects.create(**self.gym_data)
        serializer = GymSerializer(gym)

        self.assertIn("photos", serializer.data)
        self.assertEqual(serializer.data["photos"], [])
