# user_measurements/tests/test_serializers.py

from typing import cast
from decimal import Decimal
from django.test import TestCase
from users_measurements.models import Measurements
from users_measurements.serializers import UserMeasurementSerializer
from core.errors import MeasurementsError, APIError
from users.models import User
from users_measurements.serializers import MeasurementPhotosSerializer
from users_measurements.models import MeasurementPhotos
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io
from django.conf import settings


class UserMeasurementSerializerTest(TestCase):
    """Test suite for UserMeasurementSerializer"""

    def setUp(self):
        settings.DEBUG = True

        self.user = User.objects.create_user(
            phone_number="09024698787",
            first_name="Test",
            last_name="User",
        )

        self.measurement = Measurements.objects.create(
            user=self.user,
            height_cm=Decimal("175.5"),
            weight_kg=Decimal("72.3"),
            chest_cm=Decimal("102.0"),
            shoulders_cm=Decimal("115.5"),
            biceps_left_cm=Decimal("38.5"),
            biceps_right_cm=Decimal("39.0"),
            forearms_left_cm=Decimal("30.5"),
            forearms_right_cm=Decimal("31.0"),
            waist_cm=Decimal("82.0"),
            abdomen_cm=Decimal("85.5"),
            hips_cm=Decimal("95.0"),
            quadriceps_left_cm=Decimal("55.0"),
            quadriceps_right_cm=Decimal("56.0"),
            calves_left_cm=Decimal("38.0"),
            calves_right_cm=Decimal("38.5"),
            glutes_cm=Decimal("100.0"),
            measurement_notes="Initial measurements",
        )

        self.valid_data = {
            "height_cm": "180.5",
            "weight_kg": "75.0",
            "chest_cm": "105.0",
            "shoulders_cm": "118.0",
            "biceps_left_cm": "39.0",
            "biceps_right_cm": "39.5",
            "forearms_left_cm": "31.0",
            "forearms_right_cm": "31.5",
            "waist_cm": "83.0",
            "abdomen_cm": "86.0",
            "hips_cm": "96.0",
            "quadriceps_left_cm": "56.0",
            "quadriceps_right_cm": "57.0",
            "calves_left_cm": "38.5",
            "calves_right_cm": "39.0",
            "glutes_cm": "102.0",
            "measurement_notes": "Updated measurements",
        }

    def test_serializer_with_valid_data(self):
        """Test serializer with valid data"""
        serializer = UserMeasurementSerializer(
            data=self.valid_data, context={"request": None}
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["height_cm"], Decimal("180.5"))  # type: ignore
        self.assertEqual(serializer.validated_data["weight_kg"], Decimal("75.0"))  # type: ignore

    def test_serializer_with_existing_instance(self):
        """Test serializer with existing measurement instance"""
        serializer = UserMeasurementSerializer(
            instance=self.measurement, data=self.valid_data, context={"request": None}
        )
        self.assertTrue(serializer.is_valid())
        updated_measurement = serializer.save()

        self.assertEqual(updated_measurement.height_cm, Decimal("180.5"))  # type: ignore
        self.assertEqual(updated_measurement.weight_kg, Decimal("75.0"))  # type: ignore
        self.assertEqual(updated_measurement.measurement_notes, "Updated measurements")  # type: ignore

    def test_serializer_fields(self):
        """Test that serializer has correct fields"""
        serializer = UserMeasurementSerializer(
            instance=self.measurement, context={"request": None}
        )

        expected_fields = [
            "id",
            "height_cm",
            "weight_kg",
            "chest_cm",
            "shoulders_cm",
            "biceps_left_cm",
            "biceps_right_cm",
            "forearms_left_cm",
            "forearms_right_cm",
            "waist_cm",
            "abdomen_cm",
            "hips_cm",
            "quadriceps_left_cm",
            "quadriceps_right_cm",
            "calves_left_cm",
            "calves_right_cm",
            "glutes_cm",
            "photos",
            "measurement_notes",
            "created_at",
        ]

        self.assertEqual(set(serializer.data.keys()), set(expected_fields))  # type: ignore

    def test_read_only_fields(self):
        """Test that read_only fields are not writable"""
        data = self.valid_data.copy()
        data["id"] = "some-id"
        data["created_at"] = "2024-01-01T00:00:00Z"

        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

        # id and created_at should be ignored
        self.assertNotIn("id", serializer.validated_data)  # type: ignore
        self.assertNotIn("created_at", serializer.validated_data)  # type: ignore

    def test_height_validation(self):
        """Test height validation"""
        # Test too low height
        data = self.valid_data.copy()
        data["height_cm"] = "45"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_HEIGHT[0]
        )

        # Test too high height
        data["height_cm"] = "301"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_HEIGHT[0]
        )

        # Test valid height
        data["height_cm"] = "175"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

        # Test None value (should pass validation)
        data["height_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_weight_validation(self):
        """Test weight validation"""
        # Test too low weight
        data = self.valid_data.copy()
        data["weight_kg"] = "19"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_WEIGHT[0]
        )

        # Test too high weight
        data["weight_kg"] = "501"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_WEIGHT[0]
        )

        # Test valid weight
        data["weight_kg"] = "75"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

        # Test None value (should pass validation)
        data["weight_kg"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_chest_validation(self):
        """Test chest validation"""
        data = self.valid_data.copy()

        # Test too low
        data["chest_cm"] = "29"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_CHEST[0]
        )

        # Test too high
        data["chest_cm"] = "201"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_CHEST[0]
        )

        # Test valid
        data["chest_cm"] = "102"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

        # Test None value (should pass validation)
        data["chest_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_shoulders_validation(self):
        """Test shoulders validation"""
        data = self.valid_data.copy()

        # Test too low
        data["shoulders_cm"] = "29"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_SHOULDERS[0]
        )

        # Test too high
        data["shoulders_cm"] = "201"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_SHOULDERS[0]
        )

        # Test None value (should pass validation)
        data["shoulders_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_biceps_validation(self):
        """Test biceps validation"""
        data = self.valid_data.copy()

        # Test left biceps too low
        data["biceps_left_cm"] = "9"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_BICEPS[0]
        )

        # Test right biceps too high
        data["biceps_left_cm"] = "39"
        data["biceps_right_cm"] = "101"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_BICEPS[0]
        )

        # Test valid
        data["biceps_right_cm"] = "40"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

        # Test None values (should pass validation)
        data["biceps_left_cm"] = None  # type: ignore
        data["biceps_right_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_forearms_validation(self):
        """Test forearms validation"""
        data = self.valid_data.copy()

        # Test too low
        data["forearms_left_cm"] = "9"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_FOREARMS[0]
        )

        # Test too high
        data["forearms_left_cm"] = "30"
        data["forearms_right_cm"] = "81"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_FOREARMS[0]
        )

        # Test None values (should pass validation)
        data["forearms_left_cm"] = None  # type: ignore
        data["forearms_right_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_waist_validation(self):
        """Test waist validation"""
        data = self.valid_data.copy()

        # Test too low
        data["waist_cm"] = "39"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_WAIST[0]
        )

        # Test too high
        data["waist_cm"] = "251"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_WAIST[0]
        )

        # Test None value (should pass validation)
        data["waist_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_abdomen_validation(self):
        """Test abdomen validation"""
        data = self.valid_data.copy()

        # Test too low
        data["abdomen_cm"] = "39"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_ABDOMEN[0]
        )

        # Test too high
        data["abdomen_cm"] = "251"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_ABDOMEN[0]
        )

        # Test None value (should pass validation)
        data["abdomen_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_hips_validation(self):
        """Test hips validation"""
        data = self.valid_data.copy()

        # Test too low
        data["hips_cm"] = "39"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_HIPS[0]
        )

        # Test too high
        data["hips_cm"] = "251"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_HIPS[0]
        )

        # Test None value (should pass validation)
        data["hips_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_quadriceps_validation(self):
        """Test quadriceps validation"""
        data = self.valid_data.copy()

        # Test too low
        data["quadriceps_left_cm"] = "19"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_QUADRICEPS[0]
        )

        # Test too high
        data["quadriceps_left_cm"] = "50"
        data["quadriceps_right_cm"] = "151"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_QUADRICEPS[0]
        )

        # Test None values (should pass validation)
        data["quadriceps_left_cm"] = None  # type: ignore
        data["quadriceps_right_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_calves_validation(self):
        """Test calves validation"""
        data = self.valid_data.copy()

        # Test too low
        data["calves_left_cm"] = "14"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_CALVES[0]
        )

        # Test too high
        data["calves_left_cm"] = "38"
        data["calves_right_cm"] = "101"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_CALVES[0]
        )

        # Test None values (should pass validation)
        data["calves_left_cm"] = None  # type: ignore
        data["calves_right_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_glutes_validation(self):
        """Test glutes validation"""
        data = self.valid_data.copy()

        # Test too low
        data["glutes_cm"] = "39"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_GLUTES[0]
        )

        # Test too high
        data["glutes_cm"] = "251"
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.INVALID_GLUTES[0]
        )

        # Test None value (should pass validation)
        data["glutes_cm"] = None  # type: ignore
        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_serializer_partial_update(self):
        """Test partial update with serializer"""
        partial_data = {"height_cm": "180.0", "measurement_notes": "Updated notes only"}

        serializer = UserMeasurementSerializer(
            instance=self.measurement,
            data=partial_data,
            partial=True,
            context={"request": None},
        )
        self.assertTrue(serializer.is_valid())
        updated_measurement = cast(Measurements, serializer.save())

        self.assertEqual(updated_measurement.height_cm, Decimal("180.0"))
        self.assertEqual(updated_measurement.weight_kg, Decimal("72.3"))  # Unchanged
        self.assertEqual(updated_measurement.measurement_notes, "Updated notes only")

    def test_serializer_context(self):
        """Test that serializer context is properly passed"""
        request_mock = type("Request", (), {"user": self.user})()
        serializer = UserMeasurementSerializer(
            instance=self.measurement, context={"request": request_mock}
        )

        self.assertEqual(serializer.context["request"], request_mock)

    def test_serializer_with_none_values(self):
        """Test serializer with None values"""
        data = {
            "height_cm": None,
            "weight_kg": None,
            "chest_cm": None,
            "shoulders_cm": None,
            "measurement_notes": "Empty measurements",
        }

        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

        # All None values should be preserved
        self.assertIsNone(serializer.validated_data["height_cm"])  # type: ignore
        self.assertIsNone(serializer.validated_data["weight_kg"])  # type: ignore
        self.assertIsNone(serializer.validated_data["chest_cm"])  # type: ignore
        self.assertEqual(
            serializer.validated_data["measurement_notes"], "Empty measurements"  # type: ignore
        )

    def test_serializer_with_boundary_values(self):
        """Test serializer with boundary values"""
        data = {
            "height_cm": "50",  # Minimum
            "weight_kg": "20",  # Minimum
            "chest_cm": "30",  # Minimum
            "shoulders_cm": "30",  # Minimum
            "biceps_left_cm": "10",  # Minimum
            "biceps_right_cm": "10",  # Minimum
            "forearms_left_cm": "10",  # Minimum
            "forearms_right_cm": "10",  # Minimum
            "waist_cm": "40",  # Minimum
            "abdomen_cm": "40",  # Minimum
            "hips_cm": "40",  # Minimum
            "quadriceps_left_cm": "20",  # Minimum
            "quadriceps_right_cm": "20",  # Minimum
            "calves_left_cm": "15",  # Minimum
            "calves_right_cm": "15",  # Minimum
            "glutes_cm": "40",  # Minimum
        }

        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

        # Test maximum values
        data = {
            "height_cm": "300",  # Maximum
            "weight_kg": "500",  # Maximum
            "chest_cm": "200",  # Maximum
            "shoulders_cm": "200",  # Maximum
            "biceps_left_cm": "100",  # Maximum
            "biceps_right_cm": "100",  # Maximum
            "forearms_left_cm": "80",  # Maximum
            "forearms_right_cm": "80",  # Maximum
            "waist_cm": "250",  # Maximum
            "abdomen_cm": "250",  # Maximum
            "hips_cm": "250",  # Maximum
            "quadriceps_left_cm": "150",  # Maximum
            "quadriceps_right_cm": "150",  # Maximum
            "calves_left_cm": "100",  # Maximum
            "calves_right_cm": "100",  # Maximum
            "glutes_cm": "250",  # Maximum
        }

        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

    def test_serializer_with_int_precision(self):
        """Test serializer handles int precision correctly"""
        data = {
            "height_cm": "175.5",
            "weight_kg": "72.3",
            "chest_cm": "102.5",
        }

        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())
        measurement = cast(Measurements, serializer.save(user=self.user))

        # Should be rounded to 1 int place
        self.assertEqual(measurement.height_cm, Decimal("175.5"))
        self.assertEqual(measurement.weight_kg, Decimal("72.3"))
        self.assertEqual(measurement.chest_cm, Decimal("102.5"))


class UserMeasurementSerializerIntegrationTest(TestCase):
    """Integration tests for UserMeasurementSerializer with database"""

    def setUp(self):
        settings.DEBUG = True
        self.user = User.objects.create_user(
            phone_number="09024698788",
            first_name="Integration",
            last_name="Test",
        )

    def test_serializer_save_creates_new_record(self):
        """Test that serializer.save() creates a new database record"""
        data = {
            "height_cm": "170.0",
            "weight_kg": "70.0",
            "chest_cm": "100.0",
            "measurement_notes": "New measurement",
        }

        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())
        measurement = cast(Measurements, serializer.save(user=self.user))

        self.assertIsNotNone(measurement.id)
        self.assertEqual(measurement.user, self.user)
        self.assertEqual(measurement.height_cm, Decimal("170.0"))
        self.assertEqual(measurement.weight_kg, Decimal("70.0"))

    def test_serializer_save_updates_existing_record(self):
        """Test that serializer.save() updates an existing record"""
        measurement = Measurements.objects.create(
            user=self.user, height_cm=Decimal("160.0"), weight_kg=Decimal("60.0")
        )

        data = {
            "height_cm": "175.0",
            "weight_kg": "75.0",
            "measurement_notes": "Updated",
        }

        serializer = UserMeasurementSerializer(
            instance=measurement, data=data, context={"request": None}
        )
        self.assertTrue(serializer.is_valid())
        updated_measurement = cast(Measurements, serializer.save())

        self.assertEqual(updated_measurement.id, measurement.id)
        self.assertEqual(updated_measurement.height_cm, Decimal("175.0"))
        self.assertEqual(updated_measurement.weight_kg, Decimal("75.0"))

    def test_serializer_with_missing_optional_fields(self):
        """Test serializer with missing optional fields"""
        data = {"height_cm": "175.0", "weight_kg": "70.0"}

        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())
        measurement = cast(Measurements, serializer.save(user=self.user))

        self.assertIsNone(measurement.chest_cm)
        self.assertIsNone(measurement.shoulders_cm)
        self.assertEqual(measurement.measurement_notes, "")

    def test_serializer_with_extra_fields(self):
        """Test serializer ignores extra fields"""
        data = {
            "height_cm": "175.0",
            "weight_kg": "70.0",
            "extra_field": "should be ignored",
            "another_extra": 123,
        }

        serializer = UserMeasurementSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())
        self.assertNotIn("extra_field", serializer.validated_data)  # type: ignore
        self.assertNotIn("another_extra", serializer.validated_data)  # type: ignore


class MeasurementPhotosSerializerTest(TestCase):
    """Test suite for MeasurementPhotosSerializer"""

    def setUp(self):
        settings.DEBUG = True
        self.user = User.objects.create_user(
            phone_number="09024698787",
            first_name="Test",
            last_name="User",
        )
        self.measurement = Measurements.objects.create(
            user=self.user,
            height_cm=Decimal("175.5"),
            weight_kg=Decimal("72.3"),
        )

        # Create test images
        self.test_image = self.create_test_image()

    def create_test_image(self, format="JPEG", size=(100, 100)):
        """Create a test image"""
        image = Image.new("RGB", size, color="red")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format=format)
        image_bytes.seek(0)

        ext = "jpg" if format == "JPEG" else format.lower()
        return SimpleUploadedFile(
            f"test.{ext}", image_bytes.read(), content_type=f"image/{ext}"
        )

    def test_valid_photo_serializer(self):
        """Test serializer with valid data"""
        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": self.test_image,
        }

        serializer = MeasurementPhotosSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

        # Save the photo
        photo = cast(MeasurementPhotos, serializer.save(measurements=self.measurement))
        self.assertIsNotNone(photo.id)
        self.assertEqual(photo.type, MeasurementPhotos.PhotoType.FRONT)

    def test_invalid_photo_type(self):
        """Test serializer with invalid photo type"""
        data = {
            "type": "INVALID",
            "photo": self.test_image,
        }

        serializer = MeasurementPhotosSerializer(data=data, context={"request": None})

        # DRF will raise ValidationError for invalid choice
        with self.assertRaises(Exception) as context:
            serializer.is_valid(raise_exception=True)

        # Check that the error is about invalid choice
        self.assertFalse(serializer.is_valid())
        self.assertIn("type", serializer.errors)
        self.assertEqual(
            str(serializer.errors["type"][0]), '"INVALID" is not a valid choice.'  # type: ignore
        )

    def test_missing_photo_type(self):
        data = {"photo": self.test_image}

        serializer = MeasurementPhotosSerializer(data=data, context={"request": None})

        # DRF will raise a ValidationError because 'type' is a required field
        # This is the expected behavior since 'type' is required in the model
        with self.assertRaises(Exception) as context:
            serializer.is_valid(raise_exception=True)

        # Check that the error is about the missing type field
        self.assertIn("type", serializer.errors)
        self.assertEqual(str(serializer.errors["type"][0]), "This field is required.")  # type: ignore

    def test_missing_photo_file(self):
        """Test serializer with missing photo file"""
        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
        }

        serializer = MeasurementPhotosSerializer(data=data, context={"request": None})

        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.PHOTO_FILE_REQUIRED[0]
        )

    def test_large_photo_file(self):
        """Test serializer with large photo file"""
        # Create a large image (over the limit)
        large_image = self.create_test_image(size=(1000, 1000))
        # Make it larger by adding more data
        large_image.size = settings.MAX_IMAGE_SIZE + 1

        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": large_image,
        }

        serializer = MeasurementPhotosSerializer(data=data, context={"request": None})

        with self.assertRaises(APIError) as context:
            serializer.is_valid(raise_exception=True)
        self.assertEqual(
            context.exception.error_code, MeasurementsError.PHOTO_FILE_TOO_LARGE[0]
        )

    def test_invalid_file_extension(self):
        # Create a file with invalid extension
        invalid_file = SimpleUploadedFile(
            "test.txt", b"This is not an image", content_type="text/plain"
        )

        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": invalid_file,
        }

        serializer = MeasurementPhotosSerializer(data=data, context={"request": None})

        # Django's ImageField validation will catch this first
        self.assertFalse(serializer.is_valid())
        self.assertIn("photo", serializer.errors)
        self.assertEqual(
            str(serializer.errors["photo"][0]),  # type: ignore
            "Upload a valid image. The file you uploaded was either not an image or a corrupted image.",
        )

    def test_webp_conversion_on_create(self):
        """Test that image is converted to WebP on create"""
        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": self.test_image,
        }

        serializer = MeasurementPhotosSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

        photo = serializer.save(measurements=self.measurement)

        # Check that the photo is saved as WebP
        self.assertTrue(photo.photo.name.endswith(".webp"))  # type: ignore

    def test_serializer_fields(self):
        """Test serializer fields"""
        photo = MeasurementPhotos.objects.create(
            measurements=self.measurement,
            type=MeasurementPhotos.PhotoType.FRONT,
            photo=self.test_image,
        )

        serializer = MeasurementPhotosSerializer(photo)
        expected_fields = ["id", "type", "photo", "created_at"]

        self.assertEqual(set(serializer.data.keys()), set(expected_fields))  # type: ignore

    def test_read_only_fields(self):
        """Test that read_only fields cannot be written"""
        data = {
            "id": "123",
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": self.test_image,
            "created_at": "2024-01-01T00:00:00Z",
        }

        serializer = MeasurementPhotosSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid())

        # id and created_at should be ignored
        self.assertNotIn("id", serializer.validated_data)  # type: ignore
        self.assertNotIn("created_at", serializer.validated_data)  # type: ignore
