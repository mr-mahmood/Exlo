# gym_photos/tests/test_views.py
# type: ignore

import io
import uuid
from PIL import Image
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from users.models import User
from gym.models import Gym
from gym_photos.models import GymPhotos
from gym_auth.models import UserGymRole
from django.conf import settings


class GymPhotosViewsTest(TestCase):
    """Test cases for GymPhotos views."""

    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()

        # Create users
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

        # Create gym
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
        )

        UserGymRole.objects.create(
            user=self.gym_owner, gym=self.gym, role=UserGymRole.Role.OWNER
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def create_real_image(
        self, filename="test.jpg", size=(10, 10), color="red", format="JPEG"
    ):
        file = io.BytesIO()
        image = Image.new("RGB", size, color=color)
        image.save(file, format=format)
        file.seek(0)
        return SimpleUploadedFile(
            filename, file.getvalue(), content_type=f"image/{format.lower()}"
        )

    def create_fake_image(self, filename="fake.jpg"):
        return SimpleUploadedFile(
            filename, b"this is not a real image", content_type="image/jpeg"
        )

    # ==================== PHOTO LIST TESTS ====================

    def test_gym_photos_list_public_access(self):
        """Test that gym photos list is accessible without authentication."""
        photo = self.create_real_image("test.jpg")
        GymPhotos.objects.create(gym=self.gym, photo=photo)

        response = self.client.get(
            reverse("gym_photos:list", kwargs={"gym_id": self.gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("gym_photos", response.data)
        self.assertEqual(len(response.data["gym_photos"]), 1)

    def test_gym_photos_list_gym_not_found(self):
        """Test gym photos list with non-existent gym."""
        non_existent_id = uuid.uuid7()
        response = self.client.get(
            reverse("gym_photos:list", kwargs={"gym_id": non_existent_id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_photos_list_inactive_gym(self):
        """Test gym photos list with inactive gym."""
        inactive_gym = Gym.objects.create(
            name="Inactive Gym",
            province="Inactive Province",
            city="Inactive City",
            address="Inactive Address",
            is_active=False,
        )
        response = self.client.get(
            reverse("gym_photos:list", kwargs={"gym_id": inactive_gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== PHOTO CREATE TESTS ====================

    def test_gym_photo_create_admin_or_owner_only(self):
        """Test that only admin or gym owner can upload photos."""
        self.authenticate(self.regular_user)
        data = {"photos": [self.create_real_image("test1.jpg")]}
        response = self.client.post(
            reverse("gym_photos:create", kwargs={"gym_id": self.gym.id}),
            data,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.authenticate(self.gym_owner)
        data = {
            "photos": [
                self.create_real_image("test1.jpg"),
                self.create_real_image("test2.jpg"),
            ]
        }
        response = self.client.post(
            reverse("gym_photos:create", kwargs={"gym_id": self.gym.id}),
            data,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check photos were created
        photos = GymPhotos.objects.filter(gym=self.gym)
        self.assertEqual(photos.count(), 2)

    def test_gym_photo_create_fake_image_rejected(self):
        """Test that fake/invalid images are rejected."""
        fake_photo = self.create_fake_image("fake.jpg")
        data = {"photos": [fake_photo]}

        self.authenticate(self.admin_user)
        response = self.client.post(
            reverse("gym_photos:create", kwargs={"gym_id": self.gym.id}),
            data,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(GymPhotos.objects.filter(gym=self.gym).count(), 0)

    def test_gym_photo_create_no_files(self):
        """Test photo upload with no files."""
        self.authenticate(self.admin_user)
        response = self.client.post(
            reverse("gym_photos:create", kwargs={"gym_id": self.gym.id}),
            {},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gym_photo_create_gym_not_found(self):
        """Test photo upload for non-existent gym."""
        self.authenticate(self.admin_user)
        non_existent_id = uuid.uuid7()
        photo = self.create_real_image("test.jpg")
        data = {"photos": [photo]}

        response = self.client.post(
            reverse("gym_photos:create", kwargs={"gym_id": non_existent_id}),
            data,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== PHOTO DELETE TESTS ====================

    def test_gym_photo_delete_admin_or_owner_only(self):
        """Test that only admin or gym owner can delete photos."""
        photo = self.create_real_image("test.jpg")
        gym_photo = GymPhotos.objects.create(gym=self.gym, photo=photo)

        self.authenticate(self.regular_user)
        response = self.client.delete(
            reverse(
                "gym_photos:delete",
                kwargs={"gym_id": self.gym.id, "photo_id": gym_photo.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.authenticate(self.gym_owner)
        new_photo = GymPhotos.objects.create(gym=self.gym, photo=photo)
        response = self.client.delete(
            reverse(
                "gym_photos:delete",
                kwargs={"gym_id": self.gym.id, "photo_id": new_photo.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(GymPhotos.objects.filter(id=new_photo.id).exists())

    def test_gym_photo_delete_not_found(self):
        """Test photo delete with non-existent photo."""
        self.authenticate(self.admin_user)
        non_existent_id = uuid.uuid7()

        response = self.client.delete(
            reverse(
                "gym_photos:delete",
                kwargs={"gym_id": self.gym.id, "photo_id": non_existent_id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_photo_delete_owner_of_other_gym(self):
        """Test that owner of one gym cannot delete photo from another gym."""
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
        )
        photo = self.create_real_image("test.jpg")
        gym_photo = GymPhotos.objects.create(gym=other_gym, photo=photo)

        self.authenticate(self.gym_owner)
        response = self.client.delete(
            reverse(
                "gym_photos:delete",
                kwargs={"gym_id": other_gym.id, "photo_id": gym_photo.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
