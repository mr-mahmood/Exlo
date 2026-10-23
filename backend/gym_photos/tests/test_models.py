# gym_photos/tests/test_models.py


import uuid
from django.test import TestCase
from gym.models import Gym
from django.core.files.uploadedfile import SimpleUploadedFile
from gym_photos.models import GymPhotos
from django.conf import settings


class GymPhotosModelTest(TestCase):
    """Test cases for GymPhotos model."""

    def setUp(self):
        settings.DEBUG = True
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

        photos = self.gym.photos.all()
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
