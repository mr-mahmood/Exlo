# user_measurements/tests/test_models.py


from django.test import TestCase
from django.db import transaction
from unittest.mock import patch
from users.models import User
import uuid
from users_measurements.models import Measurements, MeasurementPhotos
from django.core.files.uploadedfile import SimpleUploadedFile
from decimal import Decimal
from PIL import Image
import io


class MeasurementsModelTest(TestCase):
    """Test suite for the Measurements model"""

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="09024698787",
            first_name="Test",
            last_name="User",
        )

        self.measurement_data = {
            "user": self.user,
            "height_cm": Decimal("175.5"),
            "weight_kg": Decimal("72.3"),
            "chest_cm": Decimal("102.0"),
            "shoulders_cm": Decimal("115.5"),
            "biceps_left_cm": Decimal("38.5"),
            "biceps_right_cm": Decimal("39.0"),
            "forearms_left_cm": Decimal("30.5"),
            "forearms_right_cm": Decimal("31.0"),
            "waist_cm": Decimal("82.0"),
            "abdomen_cm": Decimal("85.5"),
            "hips_cm": Decimal("95.0"),
            "quadriceps_left_cm": Decimal("55.0"),
            "quadriceps_right_cm": Decimal("56.0"),
            "calves_left_cm": Decimal("38.0"),
            "calves_right_cm": Decimal("38.5"),
            "glutes_cm": Decimal("100.0"),
            "measurement_notes": "Initial measurements",
        }

    def test_create_measurement(self):
        """Test creating a measurement with all fields"""
        measurement = Measurements.objects.create(**self.measurement_data)

        self.assertIsInstance(measurement.id, uuid.UUID)
        self.assertEqual(measurement.user, self.user)
        self.assertEqual(measurement.height_cm, Decimal("175.5"))
        self.assertEqual(measurement.weight_kg, Decimal("72.3"))
        self.assertEqual(measurement.measurement_notes, "Initial measurements")
        self.assertIsNotNone(measurement.created_at)
        self.assertIsNotNone(measurement.updated_at)
        self.assertEqual(
            str(measurement), f"{self.user.get_full_name()} - {measurement.created_at}"
        )

    def test_create_measurement_minimal_fields(self):
        """Test creating a measurement with only required fields"""
        measurement = Measurements.objects.create(user=self.user, measurement_notes="")

        self.assertIsNotNone(measurement.id)
        self.assertEqual(measurement.user, self.user)
        self.assertIsNone(measurement.height_cm)
        self.assertIsNone(measurement.weight_kg)
        self.assertEqual(measurement.measurement_notes, "")
        self.assertIsNotNone(measurement.created_at)
        self.assertIsNotNone(measurement.updated_at)

    def test_user_measurements_relationship(self):
        """Test the reverse relationship from User to Measurements"""
        measurement1 = Measurements.objects.create(user=self.user)
        measurement2 = Measurements.objects.create(user=self.user)

        user_measurements = self.user.measurements.all()

        self.assertEqual(user_measurements.count(), 2)
        self.assertIn(measurement1, user_measurements)
        self.assertIn(measurement2, user_measurements)

    def test_bmi_calculation(self):
        """Test the BMI property calculation"""
        measurement = Measurements.objects.create(
            user=self.user, height_cm=Decimal("180.0"), weight_kg=Decimal("81.0")
        )

        expected_bmi = round(81.0 / (1.8**2), 1)
        self.assertEqual(measurement.bmi, Decimal(str(expected_bmi)))

    def test_bmi_with_missing_data(self):
        """Test BMI returns None when height or weight is missing"""
        # Missing height
        measurement1 = Measurements.objects.create(
            user=self.user, weight_kg=Decimal("75.0")
        )
        self.assertIsNone(measurement1.bmi)

        # Missing weight
        measurement2 = Measurements.objects.create(
            user=self.user, height_cm=Decimal("175.0")
        )
        self.assertIsNone(measurement2.bmi)

        # Missing both
        measurement3 = Measurements.objects.create(user=self.user)
        self.assertIsNone(measurement3.bmi)

    def test_int_precision(self):
        """Test int field precision and rounding"""
        measurement = Measurements.objects.create(
            user=self.user,
            height_cm=Decimal("175.55"),
            weight_kg=Decimal("72.34"),
        )

        measurement.refresh_from_db()
        self.assertEqual(measurement.height_cm, Decimal("175.6"))
        self.assertEqual(measurement.weight_kg, Decimal("72.3"))

    def test_auto_timestamps(self):
        """Test that created_at and updated_at are automatically set"""
        measurement = Measurements.objects.create(user=self.user)

        self.assertIsNotNone(measurement.created_at)
        self.assertIsNotNone(measurement.updated_at)

        initial_created = measurement.created_at
        initial_updated = measurement.updated_at

        # Wait a moment and update
        import time

        time.sleep(0.1)

        measurement.measurement_notes = "Updated notes"
        measurement.save()
        measurement.refresh_from_db()

        self.assertEqual(measurement.created_at, initial_created)
        self.assertGreater(measurement.updated_at, initial_updated)

    def test_cascade_delete(self):
        """Test that measurements are deleted when user is deleted"""
        measurement = Measurements.objects.create(user=self.user)
        measurement_id = measurement.id

        self.user.delete()

        with self.assertRaises(Measurements.DoesNotExist):
            Measurements.objects.get(id=measurement_id)

    def test_ordering(self):
        """Test that measurements are ordered by created_at descending"""
        measurement1 = Measurements.objects.create(user=self.user)

        import time

        time.sleep(0.1)
        measurement2 = Measurements.objects.create(user=self.user)

        time.sleep(0.1)
        measurement3 = Measurements.objects.create(user=self.user)

        measurements = Measurements.objects.all()

        self.assertEqual(measurements[0], measurement3)
        self.assertEqual(measurements[1], measurement2)
        self.assertEqual(measurements[2], measurement1)

    def test_db_table_name(self):
        """Test the database table name"""
        self.assertEqual(Measurements._meta.db_table, "user_measurements")

    def test_str_method_with_full_name(self):
        """Test the string representation with user's full name"""
        measurement = Measurements.objects.create(user=self.user)

        expected = f"{self.user.get_full_name()} - {measurement.created_at}"
        self.assertEqual(str(measurement), expected)

    def test_str_method_without_full_name(self):
        """Test the string representation when user has no full name"""
        user = User.objects.create_user(
            phone_number="09136549568",
            first_name="Test2",
            last_name="User2",
        )
        measurement = Measurements.objects.create(user=user)

        expected = f"{user.get_full_name()} - {measurement.created_at}"
        self.assertEqual(str(measurement), expected)

    def test_unique_id_generation(self):
        """Test that each measurement gets a unique UUID"""
        measurement1 = Measurements.objects.create(user=self.user)
        measurement2 = Measurements.objects.create(user=self.user)

        self.assertNotEqual(measurement1.id, measurement2.id)
        self.assertIsInstance(measurement1.id, uuid.UUID)
        self.assertIsInstance(measurement2.id, uuid.UUID)

    def test_bulk_create(self):
        """Test bulk creation of measurements"""
        measurements = [
            Measurements(user=self.user, height_cm=Decimal("170.0")),
            Measurements(user=self.user, height_cm=Decimal("180.0")),
            Measurements(user=self.user, height_cm=Decimal("190.0")),
        ]

        Measurements.objects.bulk_create(measurements)

        self.assertEqual(Measurements.objects.filter(user=self.user).count(), 3)

    def test_none_values_handling(self):
        """Test that None values are handled correctly in int fields"""
        measurement = Measurements.objects.create(
            user=self.user, height_cm=None, weight_kg=None, chest_cm=None
        )

        measurement.refresh_from_db()
        self.assertIsNone(measurement.height_cm)
        self.assertIsNone(measurement.weight_kg)
        self.assertIsNone(measurement.chest_cm)

    def test_blank_notes_default(self):
        """Test that measurement_notes defaults to empty string"""
        measurement = Measurements.objects.create(user=self.user)
        self.assertEqual(measurement.measurement_notes, "")


class MeasurementsModelEdgeCasesTest(TestCase):
    """Test edge cases for the Measurements model"""

    def setUp(self):
        self.user: User = User.objects.create_user(
            phone_number="09456326565",
            first_name="Test3",
            last_name="User3",
        )

    def test_extreme_bmi_values(self):
        """Test extreme BMI values"""
        # Very low BMI (underweight)
        measurement1 = Measurements.objects.create(
            user=self.user, height_cm=Decimal("180.0"), weight_kg=Decimal("45.0")
        )
        expected_bmi1 = round(45.0 / (1.8**2), 1)
        self.assertEqual(measurement1.bmi, Decimal(str(expected_bmi1)))

        # Very high BMI (obese)
        measurement2 = Measurements.objects.create(
            user=self.user, height_cm=Decimal("160.0"), weight_kg=Decimal("150.0")
        )
        expected_bmi2 = round(150.0 / (1.6**2), 1)
        self.assertEqual(measurement2.bmi, Decimal(str(expected_bmi2)))

    def test_max_digits_constraints(self):
        """Test that int fields respect max_digits"""
        # height_cm max_digits=5, so max value is 999.9
        measurement = Measurements.objects.create(
            user=self.user, height_cm=Decimal("999.9"), weight_kg=Decimal("999.9")
        )

        measurement.refresh_from_db()
        self.assertEqual(measurement.height_cm, Decimal("999.9"))
        self.assertEqual(measurement.weight_kg, Decimal("999.9"))

    def test_zero_values(self):
        """Test zero values in measurement fields"""
        measurement = Measurements.objects.create(
            user=self.user,
            height_cm=Decimal("0.0"),
            weight_kg=Decimal("0.0"),
            chest_cm=Decimal("0.0"),
        )

        measurement.refresh_from_db()
        self.assertEqual(measurement.height_cm, Decimal("0.0"))
        self.assertEqual(measurement.weight_kg, Decimal("0.0"))
        self.assertEqual(measurement.chest_cm, Decimal("0.0"))

    def test_negative_values_handling(self):
        """Test that negative values can be stored (model doesn't prevent it)"""
        measurement = Measurements.objects.create(
            user=self.user, height_cm=Decimal("-5.0"), weight_kg=Decimal("-10.0")
        )

        measurement.refresh_from_db()
        self.assertEqual(measurement.height_cm, Decimal("-5.0"))
        self.assertEqual(measurement.weight_kg, Decimal("-10.0"))


class MeasurementPhotosModelTest(TestCase):
    """Test suite for MeasurementPhotos model"""

    def setUp(self):
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

        # Create a test image
        self.test_image = self.create_test_image()

    def create_test_image(self):
        """Create a simple test image"""
        image = Image.new("RGB", (100, 100), color="red")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="JPEG")
        image_bytes.seek(0)
        return SimpleUploadedFile(
            "test.jpg", image_bytes.read(), content_type="image/jpeg"
        )

    def _create_photo(self, photo_type=MeasurementPhotos.PhotoType.FRONT):
        return MeasurementPhotos.objects.create(
            measurements=self.measurement,
            type=photo_type,
            photo=self.create_test_image(),
        )

    def test_create_measurement_photo(self):
        """Test creating a photo for a measurement"""
        photo = MeasurementPhotos.objects.create(
            measurements=self.measurement,
            type=MeasurementPhotos.PhotoType.FRONT,
            photo=self.test_image,
        )

        self.assertIsInstance(photo.id, uuid.UUID)
        self.assertEqual(photo.measurements, self.measurement)
        self.assertEqual(photo.type, MeasurementPhotos.PhotoType.FRONT)
        self.assertIsNotNone(photo.photo)
        self.assertIsNotNone(photo.created_at)

    def test_photo_type_choices(self):
        """Test the photo type choices"""
        self.assertEqual(MeasurementPhotos.PhotoType.FRONT, "FRONT")
        self.assertEqual(MeasurementPhotos.PhotoType.BACK, "BACK")
        self.assertEqual(MeasurementPhotos.PhotoType.SIDE, "SIDE")

        self.assertEqual(MeasurementPhotos.PhotoType.FRONT.label, "Front")
        self.assertEqual(MeasurementPhotos.PhotoType.BACK.label, "Back")
        self.assertEqual(MeasurementPhotos.PhotoType.SIDE.label, "Side")

    def test_unique_measurement_type_constraint(self):
        """Test that a measurement cannot have duplicate photo types"""
        photo1 = MeasurementPhotos.objects.create(
            measurements=self.measurement,
            type=MeasurementPhotos.PhotoType.FRONT,
            photo=self.test_image,
        )

        # Try to create another photo with same type and measurement
        with self.assertRaises(Exception):  # IntegrityError
            MeasurementPhotos.objects.create(
                measurements=self.measurement,
                type=MeasurementPhotos.PhotoType.FRONT,
                photo=self.create_test_image(),
            )

    def test_measurement_photos_relationship(self):
        """Test the reverse relationship from Measurements to Photos"""
        photo1 = MeasurementPhotos.objects.create(
            measurements=self.measurement,
            type=MeasurementPhotos.PhotoType.FRONT,
            photo=self.test_image,
        )

        photo2 = MeasurementPhotos.objects.create(
            measurements=self.measurement,
            type=MeasurementPhotos.PhotoType.BACK,
            photo=self.create_test_image(),
        )

        measurement_photos = self.measurement.photos.all()

        self.assertEqual(measurement_photos.count(), 2)
        self.assertIn(photo1, measurement_photos)
        self.assertIn(photo2, measurement_photos)

    def test_cascade_delete_photos(self):
        """Test that photos are deleted when measurement is deleted"""
        photo = MeasurementPhotos.objects.create(
            measurements=self.measurement,
            type=MeasurementPhotos.PhotoType.FRONT,
            photo=self.test_image,
        )
        photo_id = photo.id
        storage = photo.photo.storage
        name = photo.photo.name

        with self.captureOnCommitCallbacks(execute=True):
            self.measurement.delete()
            self.assertTrue(storage.exists(name))

        with self.assertRaises(MeasurementPhotos.DoesNotExist):
            MeasurementPhotos.objects.get(id=photo_id)
        self.assertFalse(storage.exists(name))

    def test_queryset_deletion_removes_photo_files(self):
        photo = self._create_photo()
        storage = photo.photo.storage
        name = photo.photo.name

        with self.captureOnCommitCallbacks(execute=True):
            Measurements.objects.filter(pk=self.measurement.pk).delete()

        self.assertFalse(MeasurementPhotos.objects.filter(pk=photo.pk).exists())
        self.assertFalse(storage.exists(name))

    def test_user_cascade_removes_photo_files(self):
        photo = self._create_photo()
        storage = photo.photo.storage
        name = photo.photo.name

        with self.captureOnCommitCallbacks(execute=True):
            self.user.delete()

        self.assertFalse(Measurements.objects.filter(pk=self.measurement.pk).exists())
        self.assertFalse(MeasurementPhotos.objects.filter(pk=photo.pk).exists())
        self.assertFalse(storage.exists(name))

    def test_measurement_deletion_rollback_preserves_photos(self):
        photo = self._create_photo()
        storage = photo.photo.storage
        name = photo.photo.name

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaisesMessage(
                RuntimeError, "rollback measurement deletion"
            ):
                with transaction.atomic():
                    Measurements.objects.filter(pk=self.measurement.pk).delete()
                    self.assertTrue(storage.exists(name))
                    raise RuntimeError("rollback measurement deletion")

        self.assertEqual(callbacks, [])
        self.assertTrue(Measurements.objects.filter(pk=self.measurement.pk).exists())
        self.assertTrue(MeasurementPhotos.objects.filter(pk=photo.pk).exists())
        self.assertTrue(storage.exists(name))

    def test_cleanup_handles_empty_and_missing_files(self):
        for photo_type, name in (
            (MeasurementPhotos.PhotoType.FRONT, None),
            (MeasurementPhotos.PhotoType.BACK, ""),
            (
                MeasurementPhotos.PhotoType.SIDE,
                f"measurement_photos/{uuid.uuid7().hex}.webp",
            ),
        ):
            MeasurementPhotos.objects.create(
                measurements=self.measurement, type=photo_type, photo=name
            )

        with self.assertNoLogs("django.test", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                self.measurement.delete()

        self.assertFalse(MeasurementPhotos.objects.exists())

    def test_cleanup_failure_does_not_prevent_other_file_deletions(self):
        photos = [
            self._create_photo(photo_type) for photo_type in MeasurementPhotos.PhotoType
        ]
        storage = photos[0].photo.storage
        names = [photo.photo.name for photo in photos]
        delete_file = storage.delete
        failed_names = []

        def fail_first_deletion(name):
            if not failed_names:
                failed_names.append(name)
                raise OSError("storage unavailable")
            delete_file(name)

        with patch.object(storage, "delete", side_effect=fail_first_deletion):
            with self.assertLogs("django.test", level="ERROR") as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    self.measurement.delete()

        self.assertFalse(Measurements.objects.exists())
        self.assertFalse(MeasurementPhotos.objects.exists())
        self.assertEqual(len(failed_names), 1)
        for name in names:
            self.assertEqual(storage.exists(name), name == failed_names[0])
        self.assertIn("storage unavailable", "\n".join(logs.output))

    def test_db_table_name(self):
        """Test the database table name"""
        self.assertEqual(MeasurementPhotos._meta.db_table, "user_measurement_photos")

    def test_str_method(self):
        """Test the string representation"""
        photo = MeasurementPhotos.objects.create(
            measurements=self.measurement,
            type=MeasurementPhotos.PhotoType.FRONT,
            photo=self.test_image,
        )
        expected = f"{self.user.get_full_name()} photo - {photo.created_at}"
        self.assertEqual(str(photo), expected)

    def test_unique_together(self):
        """Test that unique_together is set correctly"""
        unique_together = MeasurementPhotos._meta.unique_together
        self.assertIn(("measurements", "type"), unique_together)
