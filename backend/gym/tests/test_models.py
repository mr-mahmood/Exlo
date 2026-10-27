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
        self.assertIsNotNone(gym.gym_code)
        self.assertIsNotNone(gym.id)
        self.assertIsInstance(gym.id, uuid.UUID)

    def test_gym_code_auto_generation(self):
        """Test that gym_code is auto-generated on creation."""
        gym1 = Gym.objects.create(name="Gym 1")
        gym2 = Gym.objects.create(name="Gym 2")

        self.assertIsNotNone(gym1.gym_code)
        self.assertIsNotNone(gym2.gym_code)
        self.assertNotEqual(gym1.gym_code, gym2.gym_code)
        self.assertEqual(len(gym1.gym_code), 6)

    def test_gym_code_uniqueness(self):
        """Test that gym_code is unique."""
        gym1 = Gym.objects.create(name="Gym 1")
        gym2 = Gym.objects.create(name="Gym 2")

        # Try to create a gym with existing code (should auto-generate new one)
        gym3 = Gym.objects.create(name="Gym 3")

        self.assertNotEqual(gym1.gym_code, gym3.gym_code)
        self.assertNotEqual(gym2.gym_code, gym3.gym_code)

    def test_gym_code_character_set(self):
        """Test that gym_code only contains allowed characters."""
        gym = Gym.objects.create(name="Test Gym")
        allowed_chars = set("23456789ABCDEFGHJKLMNPQRSTUVWXYZ")

        for char in gym.gym_code:
            self.assertIn(char, allowed_chars)

    def test_gym_str_method(self):
        """Test the __str__ method of Gym."""
        gym = Gym.objects.create(name="Test Gym")
        expected = f"{gym.name} ({gym.gym_code})"
        self.assertEqual(str(gym), expected)

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
