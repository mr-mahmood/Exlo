# gym/tests/test_views.py
# type: ignore

import io
import uuid
from PIL import Image
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch
from users.models import User
from gym.models import Gym, GymPhotos
from gym_auth.models import UserGymRole
from django.conf import settings


class GymViewsTest(TestCase):
    """Test cases for Gym views."""

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

        # Create gym with all required fields
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
        )

        # Make gym_owner the owner of the gym
        UserGymRole.objects.create(
            user=self.gym_owner, gym=self.gym, role=UserGymRole.Role.OWNER
        )

    def authenticate(self, user):
        """Helper to authenticate a user."""
        self.client.force_authenticate(user=user)

    def create_real_image(
        self,
        filename="test.jpg",
        size=(10, 10),
        color="red",
        format="JPEG",
    ):
        """Helper to create a valid real test image."""
        file = io.BytesIO()
        image = Image.new("RGB", size, color=color)
        image.save(file, format=format)
        file.seek(0)

        return SimpleUploadedFile(
            filename, file.getvalue(), content_type=f"image/{format.lower()}"
        )

    def create_fake_image(self, filename="fake.jpg"):
        """Helper to create a fake invalid image."""
        return SimpleUploadedFile(
            filename, b"this is not a real image", content_type="image/jpeg"
        )

    # ==================== GYM LIST TESTS ====================

    def test_gym_list_public_access(self):
        """Test that gym list is accessible without authentication."""
        response = self.client.get(reverse("gym-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("gyms", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)

    def test_gym_list_returns_only_active_gyms(self):
        """Test that gym list returns only active gyms."""
        # Create inactive gym with all required fields
        inactive_gym = Gym.objects.create(
            name="Inactive Gym",
            province="Inactive Province",
            city="Inactive City",
            address="Inactive Address",
            is_active=False,
        )

        response = self.client.get(reverse("gym-list"))
        gym_ids = [gym["id"] for gym in response.data["gyms"]]

        self.assertIn(str(self.gym.id), gym_ids)
        self.assertNotIn(str(inactive_gym.id), gym_ids)

    # ==================== GYM DETAIL TESTS ====================

    def test_gym_detail_public_access(self):
        """Test that gym detail is accessible without authentication."""
        response = self.client.get(
            reverse("gym-detail", kwargs={"gym_id": self.gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["id"], str(self.gym.id))
        self.assertEqual(response.data["gym"]["name"], "Test Gym")
        self.assertEqual(response.data["gym"]["province"], "Test Province")
        self.assertEqual(response.data["gym"]["city"], "Test City")
        self.assertEqual(response.data["gym"]["address"], "123 Test St")

    def test_gym_detail_not_found(self):
        """Test gym detail with non-existent gym ID."""
        non_existent_id = uuid.uuid4()
        response = self.client.get(
            reverse("gym-detail", kwargs={"gym_id": non_existent_id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_detail_inactive_gym(self):
        """Test that inactive gym returns 404."""
        inactive_gym = Gym.objects.create(
            name="Inactive Gym",
            province="Inactive Province",
            city="Inactive City",
            address="Inactive Address",
            is_active=False,
        )
        response = self.client.get(
            reverse("gym-detail", kwargs={"gym_id": inactive_gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== GYM CREATE TESTS ====================

    def test_gym_create_admin_only(self):
        """Test that only admin can create gym."""
        data = {
            "name": "New Gym",
            "province": "New Province",
            "city": "New City",
            "address": "456 New St",
        }

        # Regular user cannot create
        self.authenticate(self.regular_user)
        response = self.client.post(reverse("gym-create"), data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Gym owner cannot create
        self.authenticate(self.gym_owner)
        response = self.client.post(reverse("gym-create"), data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Admin can create
        self.authenticate(self.admin_user)
        response = self.client.post(reverse("gym-create"), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["gym"]["name"], "New Gym")
        self.assertEqual(response.data["gym"]["province"], "New Province")
        self.assertEqual(response.data["gym"]["city"], "New City")
        self.assertEqual(response.data["gym"]["address"], "456 New St")
        self.assertIsNotNone(response.data["gym"]["gym_code"])

    def test_gym_create_missing_name(self):
        """Test gym creation with missing name."""
        self.authenticate(self.admin_user)

        data = {
            "province": "New Province",
            "city": "New City",
            "address": "456 New St",
        }
        response = self.client.post(reverse("gym-create"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gym_create_missing_province(self):
        """Test gym creation with missing province."""
        self.authenticate(self.admin_user)

        data = {
            "name": "New Gym",
            "city": "New City",
            "address": "456 New St",
        }
        response = self.client.post(reverse("gym-create"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gym_create_missing_city(self):
        """Test gym creation with missing city."""
        self.authenticate(self.admin_user)

        data = {
            "name": "New Gym",
            "province": "New Province",
            "address": "456 New St",
        }
        response = self.client.post(reverse("gym-create"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gym_create_missing_address(self):
        """Test gym creation with missing address."""
        self.authenticate(self.admin_user)

        data = {
            "name": "New Gym",
            "province": "New Province",
            "city": "New City",
        }
        response = self.client.post(reverse("gym-create"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gym_create_missing_multiple_fields(self):
        """Test gym creation with multiple missing required fields."""
        self.authenticate(self.admin_user)

        data = {"name": "New Gym"}  # Missing province, city, address
        response = self.client.post(reverse("gym-create"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==================== GYM UPDATE TESTS ====================

    def test_gym_update_admin_or_owner_only(self):
        """Test that only admin or gym owner can update gym."""
        data = {"name": "Updated Gym Name"}

        # Regular user cannot update
        self.authenticate(self.regular_user)
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": self.gym.id}), data
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Gym owner can update
        self.authenticate(self.gym_owner)
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": self.gym.id}), data
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["name"], "Updated Gym Name")
        self.assertEqual(response.data["gym"]["province"], "Test Province")
        self.assertEqual(response.data["gym"]["city"], "Test City")
        self.assertEqual(response.data["gym"]["address"], "123 Test St")

        # Admin can update
        self.gym.name = "Test Gym"  # Reset
        self.gym.save()

        self.authenticate(self.admin_user)
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": self.gym.id}), data
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["name"], "Updated Gym Name")

    def test_gym_update_owner_of_other_gym(self):
        """Test that owner of one gym cannot update another gym."""
        # Create another gym with all required fields
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
        )

        data = {"name": "Hacked Gym Name"}

        self.authenticate(self.gym_owner)
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": other_gym.id}), data
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_update_not_found(self):
        """Test gym update with non-existent gym ID."""
        self.authenticate(self.admin_user)
        non_existent_id = uuid.uuid4()

        data = {"name": "Updated Name"}
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": non_existent_id}), data
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_update_partial(self):
        """Test partial update of gym."""
        self.authenticate(self.admin_user)

        data = {"city": "New City"}
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": self.gym.id}), data
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["city"], "New City")
        self.assertEqual(response.data["gym"]["name"], "Test Gym")  # Unchanged
        self.assertEqual(response.data["gym"]["province"], "Test Province")
        self.assertEqual(response.data["gym"]["address"], "123 Test St")

    def test_gym_update_partial_all_fields(self):
        """Test partial update of all fields."""
        self.authenticate(self.admin_user)

        data = {
            "name": "Updated Name",
            "province": "Updated Province",
            "city": "Updated City",
            "address": "Updated Address",
        }
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": self.gym.id}), data
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["name"], "Updated Name")
        self.assertEqual(response.data["gym"]["province"], "Updated Province")
        self.assertEqual(response.data["gym"]["city"], "Updated City")
        self.assertEqual(response.data["gym"]["address"], "Updated Address")

    # ==================== GYM DELETE TESTS ====================

    def test_gym_delete_admin_or_owner_only(self):
        """Test that only admin or gym owner can delete gym."""
        # Regular user cannot delete
        self.authenticate(self.regular_user)
        response = self.client.delete(
            reverse("gym-delete", kwargs={"gym_id": self.gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Gym owner can delete (mock has_active_memberships)
        self.authenticate(self.gym_owner)
        with patch.object(Gym, "has_active_memberships", return_value=False):
            response = self.client.delete(
                reverse("gym-delete", kwargs={"gym_id": self.gym.id})
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Admin can delete
        new_gym = Gym.objects.create(
            name="New Gym",
            province="New Province",
            city="New City",
            address="New Address",
        )
        self.authenticate(self.admin_user)
        with patch.object(Gym, "has_active_memberships", return_value=False):
            response = self.client.delete(
                reverse("gym-delete", kwargs={"gym_id": new_gym.id})
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_gym_delete_owner_of_other_gym(self):
        """Test that owner of one gym cannot delete another gym."""
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
        )

        self.authenticate(self.gym_owner)
        response = self.client.delete(
            reverse("gym-delete", kwargs={"gym_id": other_gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_delete_not_found(self):
        """Test gym delete with non-existent gym ID."""
        self.authenticate(self.admin_user)
        non_existent_id = uuid.uuid4()

        response = self.client.delete(
            reverse("gym-delete", kwargs={"gym_id": non_existent_id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_delete_with_active_memberships(self):
        """Test deleting gym with active memberships fails."""
        # Mock has_active_memberships to return True
        with patch.object(Gym, "has_active_memberships", return_value=True):
            self.authenticate(self.admin_user)
            response = self.client.delete(
                reverse("gym-delete", kwargs={"gym_id": self.gym.id})
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==================== GYM PHOTOS TESTS ====================

    def test_gym_photos_list_public_access(self):
        """Test that gym photos list is accessible without authentication."""
        # Create a real photo
        photo = self.create_real_image("test.jpg")
        GymPhotos.objects.create(gym=self.gym, photo=photo)

        response = self.client.get(
            reverse("gym-photos", kwargs={"gym_id": self.gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("gym_photos", response.data)
        self.assertEqual(len(response.data["gym_photos"]), 1)

    def test_gym_photos_list_gym_not_found(self):
        """Test gym photos list with non-existent gym."""
        non_existent_id = uuid.uuid4()
        response = self.client.get(
            reverse("gym-photos", kwargs={"gym_id": non_existent_id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_photos_list_inactive_gym(self):
        inactive_gym = Gym.objects.create(
            name="Inactive Gym",
            province="Inactive Province",
            city="Inactive City",
            address="Inactive Address",
            is_active=False,
        )
        response = self.client.get(
            reverse("gym-photos", kwargs={"gym_id": inactive_gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_photo_create_admin_or_owner_only(self):
        """Test that only admin or gym owner can upload photos."""

        # Regular user cannot upload
        self.authenticate(self.regular_user)

        data = {
            "photos": [
                self.create_real_image("test1.jpg", color="red"),
                self.create_real_image("test2.jpg", color="blue"),
            ]
        }

        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": self.gym.id}),
            data,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Gym owner can upload
        self.authenticate(self.gym_owner)

        data = {
            "photos": [
                self.create_real_image("test1.jpg", color="red"),
                self.create_real_image("test2.jpg", color="blue"),
            ]
        }

        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": self.gym.id}),
            data,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Admin can upload
        self.authenticate(self.admin_user)

        data = {
            "photos": [
                self.create_real_image("test1.jpg", color="red"),
                self.create_real_image("test2.jpg", color="blue"),
            ]
        }

        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": self.gym.id}),
            data,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_gym_photo_create_fake_image_rejected(self):
        """Test that fake/invalid images are rejected."""
        fake_photo = self.create_fake_image("fake.jpg")
        data = {"photos": [fake_photo]}

        self.authenticate(self.admin_user)
        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": self.gym.id}),
            data,
            format="multipart",
        )

        # Should return 400 because image is invalid
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # No photos should be created
        photos = GymPhotos.objects.filter(gym=self.gym)
        self.assertEqual(photos.count(), 0)

    def test_gym_photo_create_mixed_files(self):
        """Test uploading mixed valid and invalid images."""
        real_photo = self.create_real_image("real.jpg")
        fake_photo = self.create_fake_image("fake.jpg")
        data = {"photos": [real_photo, fake_photo]}

        self.authenticate(self.admin_user)
        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": self.gym.id}),
            data,
            format="multipart",
        )

        # Should fail because one of the files is invalid
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # No photos should be created (atomic behavior)
        photos = GymPhotos.objects.filter(gym=self.gym)
        self.assertEqual(photos.count(), 0)

    def test_gym_photo_create_no_files(self):
        """Test photo upload with no files."""
        self.authenticate(self.admin_user)
        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": self.gym.id}),
            {},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gym_photo_create_multiple_files(self):
        """Test uploading multiple real photos."""
        photo1 = self.create_real_image("test1.jpg", color="red")
        photo2 = self.create_real_image("test2.jpg", color="blue")
        data = {"photos": [photo1, photo2]}

        self.authenticate(self.admin_user)
        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": self.gym.id}),
            data,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check that both photos were created
        photos = GymPhotos.objects.filter(gym=self.gym)
        self.assertEqual(photos.count(), 2)

    def test_gym_photo_create_gym_not_found(self):
        """Test photo upload for non-existent gym."""
        self.authenticate(self.admin_user)
        non_existent_id = uuid.uuid4()
        photo = self.create_real_image("test.jpg")
        data = {"photos": [photo]}

        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": non_existent_id}),
            data,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_photo_delete_admin_or_owner_only(self):
        """Test that only admin or gym owner can delete photos."""
        photo = self.create_real_image("test.jpg")
        gym_photo = GymPhotos.objects.create(gym=self.gym, photo=photo)

        # Regular user cannot delete
        self.authenticate(self.regular_user)
        response = self.client.delete(
            reverse(
                "gym-photo-delete",
                kwargs={"gym_id": self.gym.id, "photo_id": gym_photo.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Gym owner can delete
        self.authenticate(self.gym_owner)
        new_photo = GymPhotos.objects.create(gym=self.gym, photo=photo)
        response = self.client.delete(
            reverse(
                "gym-photo-delete",
                kwargs={"gym_id": self.gym.id, "photo_id": new_photo.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(GymPhotos.objects.filter(id=new_photo.id).exists())

        # Admin can delete
        new_photo = GymPhotos.objects.create(gym=self.gym, photo=photo)
        self.authenticate(self.admin_user)
        response = self.client.delete(
            reverse(
                "gym-photo-delete",
                kwargs={"gym_id": self.gym.id, "photo_id": new_photo.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(GymPhotos.objects.filter(id=new_photo.id).exists())

    def test_gym_photo_delete_not_found(self):
        """Test photo delete with non-existent photo."""
        self.authenticate(self.admin_user)
        non_existent_id = uuid.uuid4()

        response = self.client.delete(
            reverse(
                "gym-photo-delete",
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
                "gym-photo-delete",
                kwargs={"gym_id": other_gym.id, "photo_id": gym_photo.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== PERMISSION TESTS ====================

    def test_is_gym_owner_permission(self):
        """Test that IsGymOwner permission works correctly."""
        # Gym owner should have access
        self.authenticate(self.gym_owner)
        response = self.client.get(
            reverse("gym-detail", kwargs={"gym_id": self.gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Regular user should not have owner access
        self.authenticate(self.regular_user)
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": self.gym.id}), {"name": "Hacked"}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_has_access_to_all_gyms(self):
        """Test that admin can access and manage any gym."""
        # Create another gym where admin is NOT the owner
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
        )

        self.authenticate(self.admin_user)

        # Admin can view other gym
        response = self.client.get(
            reverse("gym-detail", kwargs={"gym_id": other_gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Admin can update other gym
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": other_gym.id}),
            {"name": "Updated By Admin"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["name"], "Updated By Admin")

        # Admin can delete other gym
        with patch.object(Gym, "has_active_memberships", return_value=False):
            response = self.client.delete(
                reverse("gym-delete", kwargs={"gym_id": other_gym.id})
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_owner_cannot_access_other_gym(self):
        """Test that gym owner cannot access or manage other gyms."""
        # Create another gym
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
        )

        self.authenticate(self.gym_owner)

        # Gym owner can view other gym (public)
        response = self.client.get(
            reverse("gym-detail", kwargs={"gym_id": other_gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Gym owner cannot update other gym
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": other_gym.id}), {"name": "Hacked"}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Gym owner cannot delete other gym
        response = self.client.delete(
            reverse("gym-delete", kwargs={"gym_id": other_gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_cannot_upload_photos_to_other_gym(self):
        """Test that gym owner cannot upload photos to other gyms."""
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
        )
        photo = self.create_real_image("test.jpg")
        data = {"photos": [photo]}

        self.authenticate(self.gym_owner)
        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": other_gym.id}),
            data,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_cannot_delete_photos_from_other_gym(self):
        """Test that gym owner cannot delete photos from other gyms."""
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
                "gym-photo-delete",
                kwargs={"gym_id": other_gym.id, "photo_id": gym_photo.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_regular_user_no_access_to_protected_endpoints(self):
        """Test that regular user has no access to protected endpoints."""
        self.authenticate(self.regular_user)

        # Cannot update
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": self.gym.id}), {"name": "Updated"}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Cannot delete
        response = self.client.delete(
            reverse("gym-delete", kwargs={"gym_id": self.gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Cannot upload photos
        photo = self.create_real_image("test.jpg")
        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": self.gym.id}),
            {"photos": [photo]},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Cannot delete photos
        gym_photo = GymPhotos.objects.create(
            gym=self.gym,
            photo=self.create_real_image("test.jpg"),
        )
        response = self.client.delete(
            reverse(
                "gym-photo-delete",
                kwargs={"gym_id": self.gym.id, "photo_id": gym_photo.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_is_admin_or_gym_owner_permission_with_owner(self):
        """Test IsAdminOrGymOwner permission works with gym owner."""
        self.authenticate(self.gym_owner)

        # Owner can update own gym
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": self.gym.id}),
            {"name": "Updated By Owner"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["name"], "Updated By Owner")

        # Owner can delete own gym
        with patch.object(Gym, "has_active_memberships", return_value=False):
            response = self.client.delete(
                reverse("gym-delete", kwargs={"gym_id": self.gym.id})
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_is_admin_or_gym_owner_permission_with_admin(self):
        """Test IsAdminOrGymOwner permission works with admin."""
        self.authenticate(self.admin_user)

        # Admin can update any gym
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": self.gym.id}),
            {"name": "Updated By Admin"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gym"]["name"], "Updated By Admin")

        # Admin can delete any gym
        with patch.object(Gym, "has_active_memberships", return_value=False):
            response = self.client.delete(
                reverse("gym-delete", kwargs={"gym_id": self.gym.id})
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unauthenticated_user_cannot_access_protected_endpoints(self):
        """Test that unauthenticated users cannot access protected endpoints."""
        data = {
            "name": "New Gym",
            "province": "New Province",
            "city": "New City",
            "address": "456 New St",
        }

        # Create (admin only)
        response = self.client.post(reverse("gym-create"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Update
        response = self.client.put(
            reverse("gym-update", kwargs={"gym_id": self.gym.id}), data
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Delete
        response = self.client.delete(
            reverse("gym-delete", kwargs={"gym_id": self.gym.id})
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Photo create
        photo = self.create_real_image("test.jpg")
        response = self.client.post(
            reverse("gym-photo-create", kwargs={"gym_id": self.gym.id}),
            {"photos": [photo]},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Photo delete
        gym_photo = GymPhotos.objects.create(
            gym=self.gym,
            photo=self.create_real_image("test.jpg"),
        )
        response = self.client.delete(
            reverse(
                "gym-photo-delete",
                kwargs={"gym_id": self.gym.id, "photo_id": gym_photo.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
