# gym/tests/test_models.py

import uuid
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from gym.models import Gym, GymPhotos
from django.core.files.uploadedfile import SimpleUploadedFile


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

    def test_gym_has_active_memberships(self):
        """Test has_active_memberships method."""
        gym = Gym.objects.create(name="Test Gym")
        # TODO: Update when membership tables are added
        self.assertTrue(gym.has_active_memberships())

    def test_gym_ordering(self):
        """Test that gyms are ordered by created_at descending."""
        gym1 = Gym.objects.create(name="Gym 1")
        gym2 = Gym.objects.create(name="Gym 2")
        gym3 = Gym.objects.create(name="Gym 3")

        gyms = Gym.objects.all()
        self.assertEqual(gyms[0], gym3)  # Most recent first
        self.assertEqual(gyms[1], gym2)
        self.assertEqual(gyms[2], gym1)

    def test_gym_indexes(self):
        """Test that indexes are created."""
        indexes = Gym._meta.indexes
        index_names = [index.name for index in indexes]

        self.assertIn("name_idx", index_names)
        self.assertIn("gym_code_idx", index_names)
        self.assertIn("gym_created_at_idx", index_names)


class GymPhotosModelTest(TestCase):
    """Test cases for GymPhotos model."""

    def setUp(self):
        self.gym = Gym.objects.create(name="Test Gym")
        self.photo_content = b"fake image content"
        self.photo = SimpleUploadedFile(
            "test_photo.jpg", self.photo_content, content_type="image/jpeg"
        )

    def test_create_gym_photo_success(self):
        """Test creating a gym photo successfully."""
        gym_photo = GymPhotos.objects.create(gym=self.gym, photo=self.photo)

        self.assertEqual(gym_photo.gym, self.gym)
        self.assertIsNotNone(gym_photo.photo)
        self.assertIsNotNone(gym_photo.id)
        self.assertIsInstance(gym_photo.id, uuid.UUID)

    def test_gym_photo_related_name(self):
        """Test accessing photos through gym's related_name."""
        gym_photo1 = GymPhotos.objects.create(gym=self.gym, photo=self.photo)
        gym_photo2 = GymPhotos.objects.create(gym=self.gym, photo=self.photo)

        photos = self.gym.photos.all()  # type: ignore
        self.assertEqual(photos.count(), 2)
        self.assertIn(gym_photo1, photos)
        self.assertIn(gym_photo2, photos)

    def test_gym_photo_cascade_delete(self):
        """Test that photos are deleted when gym is deleted."""
        gym_photo = GymPhotos.objects.create(gym=self.gym, photo=self.photo)
        gym_id = self.gym.id

        self.gym.delete()

        with self.assertRaises(GymPhotos.DoesNotExist):
            GymPhotos.objects.get(id=gym_photo.id)

        # Gym should be deleted
        with self.assertRaises(Gym.DoesNotExist):
            Gym.objects.get(id=gym_id)

    def test_gym_photo_str_method(self):
        """Test the __str__ method of GymPhotos."""
        gym_photo = GymPhotos.objects.create(gym=self.gym, photo=self.photo)
        expected = f"{self.gym.name} photo - {gym_photo.created_at}"
        self.assertEqual(str(gym_photo), expected)

    def test_gym_photo_ordering(self):
        """Test that photos are ordered by created_at descending."""
        photo1 = GymPhotos.objects.create(gym=self.gym, photo=self.photo)
        photo2 = GymPhotos.objects.create(gym=self.gym, photo=self.photo)

        photos = GymPhotos.objects.all()
        self.assertEqual(photos[0], photo2)  # Most recent first
        self.assertEqual(photos[1], photo1)

    def test_gym_photo_indexes(self):
        """Test that indexes are created."""
        indexes = GymPhotos._meta.indexes
        index_names = [index.name for index in indexes]

        self.assertIn("gym_photo_created_at_idx", index_names)
