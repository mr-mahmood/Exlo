# gym/tests/test_models.py


import uuid
from django.test import TestCase
from gym.models import Gym
from django.conf import settings


class GymModelTest(TestCase):
    """Test cases for Gym model."""

    def setUp(self):
        self.gym_data = {
            "name": "Test Gym",
            "province": "Test Province",
            "city": "Test City",
            "address": "123 Test St",
            "latitude": "40.7128",
            "longitude": "-74.0060",
        }

    def test_create_gym_success(self):
        """Test creating a gym successfully."""
        gym = Gym.objects.create(**self.gym_data)

        self.assertEqual(gym.name, "Test Gym")
        self.assertEqual(gym.province, "Test Province")
        self.assertEqual(gym.city, "Test City")
        self.assertEqual(gym.address, "123 Test St")
        self.assertEqual(gym.latitude, "40.7128")
        self.assertEqual(gym.longitude, "-74.0060")
        self.assertTrue(gym.is_active)
        self.assertIsNotNone(gym.id)
        self.assertIsInstance(gym.id, uuid.UUID)

    def test_gym_activate(self):
        """Test activating a gym."""
        gym = Gym.objects.create(name="Test Gym", is_active=False)
        gym.activate()

        gym.refresh_from_db()
        self.assertTrue(gym.is_active)

    def test_gym_deactivate(self):
        """Test deactivating a gym."""
        gym = Gym.objects.create(name="Test Gym", is_active=True)
        gym.deactivate()

        gym.refresh_from_db()
        self.assertFalse(gym.is_active)

    def test_gym_ordering(self):
        """Test that gyms are ordered by created_at descending."""
        gym1 = Gym.objects.create(name="Gym 1")
        gym2 = Gym.objects.create(name="Gym 2")
        gym3 = Gym.objects.create(name="Gym 3")

        gyms = Gym.objects.all()
        self.assertEqual(gyms[0], gym3)  # Most recent first
        self.assertEqual(gyms[1], gym2)
        self.assertEqual(gyms[2], gym1)
