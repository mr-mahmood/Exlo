# gym_photos/tests/test_serializers.py
# type: ignore

import io
import uuid
from PIL import Image
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from gym.models import Gym
from gym_photos.serializers import GymPhotoSerializer
from core.errors import APIError, GymError
from django.conf import settings


class GymPhotoSerializerTest(TestCase):
    """Test cases for GymPhotoSerializer."""

    def setUp(self):
        settings.DEBUG = True
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
        )
        self.photo_data = self.create_test_image()

    def create_test_image(self, size_kb=100, format="JPEG"):
        """Helper to create a test image."""
        file = io.BytesIO()
        image = Image.new("RGB", (100, 100), color="red")
        image.save(file, format=format)
        file.seek(0)

        return SimpleUploadedFile(
            f"test.{format.lower()}",
            file.getvalue(),
            content_type=f"image/{format.lower()}",
        )

    def test_serializer_valid_data(self):
        """Test serializer with valid data."""
        data = {"photo": self.photo_data}
        serializer = GymPhotoSerializer(
            data=data, context={"gym": self.gym}  # Add context
        )
        self.assertTrue(serializer.is_valid())

        # Save should work now
        gym_photo = serializer.save()
        self.assertIsNotNone(gym_photo)
        self.assertEqual(gym_photo.gym, self.gym)

    def test_serializer_missing_photo(self):
        """Test serializer with missing photo."""
        data = {}
        serializer = GymPhotoSerializer(
            data=data, context={"gym": self.gym}  # Add context
        )

        # Serializer validation should fail
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(context.exception.error_code, GymError.PHOTO_FILE_REQUIRED[0])

    def test_serializer_invalid_extension(self):
        """Test serializer with invalid file extension."""
        photo = SimpleUploadedFile(
            "test.txt", b"fake content", content_type="text/plain"
        )

        data = {"photo": photo}
        serializer = GymPhotoSerializer(
            data=data, context={"gym": self.gym}  # Add context
        )

        with self.assertRaises(DRFValidationError) as context:
            serializer.is_valid(raise_exception=True)

    def test_serializer_invalid_image_file(self):
        """Test serializer with invalid image file."""
        photo = SimpleUploadedFile(
            "fake.jpg", b"this is not an image", content_type="image/jpeg"
        )

        data = {"photo": photo}
        serializer = GymPhotoSerializer(
            data=data, context={"gym": self.gym}  # Add context
        )

        with self.assertRaises(DRFValidationError) as context:
            serializer.is_valid(raise_exception=True)

    def test_serializer_photo_conversion_to_webp(self):
        """Test that photo is converted to WebP format."""
        data = {"photo": self.photo_data}
        serializer = GymPhotoSerializer(
            data=data, context={"gym": self.gym}  # Add context
        )
        self.assertTrue(serializer.is_valid())

        gym_photo = serializer.save()
        self.assertIsNotNone(gym_photo.photo)
        self.assertTrue(gym_photo.photo.name.endswith(".webp"))

    def test_serializer_photo_conversion_failed(self):
        """Test photo conversion failure handling."""
        # Create a corrupted image - this should fail validation
        # because Image.open() will fail
        corrupted_file = SimpleUploadedFile(
            "corrupted.jpg", b"corrupted image data", content_type="image/jpeg"
        )

        data = {"photo": corrupted_file}
        serializer = GymPhotoSerializer(
            data=data, context={"gym": self.gym}  # Add context
        )

        # This should fail validation because the image is corrupted
        with self.assertRaises(DRFValidationError) as context:
            serializer.is_valid(raise_exception=True)

    def test_serializer_photo_quality_optimization(self):
        """Test that photo quality is optimized."""
        data = {"photo": self.photo_data}
        serializer = GymPhotoSerializer(
            data=data, context={"gym": self.gym}  # Add context
        )
        self.assertTrue(serializer.is_valid())

        gym_photo = serializer.save()

        # Check that the file is smaller (optimized)
        original_size = self.photo_data.size
        converted_size = gym_photo.photo.size

        # WebP with 85 quality should be smaller
        self.assertLess(converted_size, original_size)

    def test_serializer_read_only_fields(self):
        """Test that read-only fields are not writable."""
        data = {
            "photo": self.photo_data,
            "id": str(uuid.uuid7()),
            "created_at": "2024-01-01T00:00:00Z",
        }
        serializer = GymPhotoSerializer(
            data=data, context={"gym": self.gym}  # Add context
        )
        self.assertTrue(serializer.is_valid())

        gym_photo = serializer.save()
        self.assertNotEqual(str(gym_photo.id), data["id"])
