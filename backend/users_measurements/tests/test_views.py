# user_measurements/tests/test_views.py


from django.test import TestCase
from decimal import Decimal
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from users_measurements.models import Measurements
from core.errors import MeasurementsError
from users.models import User
from users_measurements.models import MeasurementPhotos
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io
from django.core.files.storage import default_storage


class UserMeasurementsListViewTest(TestCase):
    """Test suite for UserMeasurementsListView"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number="09024698787",
            first_name="Test",
            last_name="User",
        )
        self.url = reverse("user_measurements:list")
        self.create_url = reverse("user_measurements:create")

        # Create some measurements
        self.measurement1 = Measurements.objects.create(
            user=self.user,
            height_cm=Decimal("175.5"),
            weight_kg=Decimal("72.3"),
            chest_cm=Decimal("102.0"),
            measurement_notes="First measurement",
        )

        self.measurement2 = Measurements.objects.create(
            user=self.user,
            height_cm=Decimal("180.0"),
            weight_kg=Decimal("75.0"),
            chest_cm=Decimal("105.0"),
            measurement_notes="Second measurement",
        )

    def test_get_measurements_authenticated(self):
        """Test GET measurements with authenticated user"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("measurements", response.data)
        self.assertEqual(len(response.data["measurements"]), 2)

        # Check that the measurements are ordered by created_at descending
        self.assertEqual(
            response.data["measurements"][0]["measurement_notes"],
            "Second measurement",
        )
        self.assertEqual(
            response.data["measurements"][1]["measurement_notes"],
            "First measurement",
        )

    def test_get_measurements_unauthenticated(self):
        """Test GET measurements without authentication"""
        response = self.client.get(self.url)
        # The API returns 400 for unauthenticated requests
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_measurements_no_measurements(self):
        """Test GET measurements when user has no measurements"""
        new_user = User.objects.create_user(
            phone_number="09123456789",
            first_name="New",
            last_name="User",
            password="testpass123",
        )
        self.client.force_authenticate(user=new_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["measurements"], [])

    def test_get_measurements_pagination(self):
        """Test GET measurements with pagination"""
        # Create more measurements to test pagination
        for i in range(10):
            Measurements.objects.create(
                user=self.user,
                height_cm=Decimal("170.0") + Decimal(str(i)),
                weight_kg=Decimal("70.0") + Decimal(str(i)),
            )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Custom pagination may not return 'count' - check for pagination structure
        self.assertIn("measurements", response.data)
        # Check that we have pagination info (next, previous)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)

    def test_post_measurement_authenticated(self):
        """Test POST measurement with authenticated user"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "185.0",
            "weight_kg": "80.0",
            "chest_cm": "110.0",
            "shoulders_cm": "120.0",
            "measurement_notes": "New measurement",
        }

        response = self.client.post(self.create_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("measurement", response.data)
        self.assertEqual(response.data["measurement"]["height_cm"], "185.0")
        self.assertEqual(response.data["measurement"]["weight_kg"], "80.0")
        self.assertEqual(
            response.data["measurement"]["measurement_notes"],
            "New measurement",
        )

        # Verify it was saved in database
        self.assertEqual(Measurements.objects.filter(user=self.user).count(), 3)

    def test_post_measurement_unauthenticated(self):
        """Test POST measurement without authentication"""
        data = {
            "height_cm": "185.0",
            "weight_kg": "80.0",
        }
        response = self.client.post(self.create_url, data, format="json")
        # The API returns 400 for unauthenticated requests
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

    def test_post_measurement_invalid_data(self):
        """Test POST measurement with invalid data"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "45",  # Too low
            "weight_kg": "80.0",
        }

        response = self.client.post(self.create_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.INVALID_HEIGHT[0],
        )

    def test_post_measurement_with_minimal_data(self):
        """Test POST measurement with minimal required data"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "175.0",
            "weight_kg": "70.0",
        }

        response = self.client.post(self.create_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("measurement", response.data)
        self.assertEqual(response.data["measurement"]["height_cm"], "175.0")
        self.assertEqual(response.data["measurement"]["weight_kg"], "70.0")
        self.assertEqual(response.data["measurement"]["measurement_notes"], "")

    def test_post_measurement_with_extra_fields(self):
        """Test POST measurement with extra fields (should be ignored)"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "175.0",
            "weight_kg": "70.0",
            "extra_field": "ignored",
        }

        response = self.client.post(self.create_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("extra_field", response.data["measurement"])

    # ========== EDGE CASE TESTS ==========

    def test_post_measurement_with_empty_data(self):
        """Test POST with empty data - should return 400 Bad Request"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.create_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            "MEAS_022",  # The new error code
        )

    def test_post_measurement_with_null_values(self):
        """Test POST with null values for all fields"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": None,
            "weight_kg": None,
            "chest_cm": None,
            "shoulders_cm": None,
            "biceps_left_cm": None,
            "biceps_right_cm": None,
            "forearms_left_cm": None,
            "forearms_right_cm": None,
            "waist_cm": None,
            "abdomen_cm": None,
            "hips_cm": None,
            "quadriceps_left_cm": None,
            "quadriceps_right_cm": None,
            "calves_left_cm": None,
            "calves_right_cm": None,
            "glutes_cm": None,
            "measurement_notes": "",
        }
        response = self.client.post(self.create_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["measurement"]["height_cm"])
        self.assertIsNone(response.data["measurement"]["weight_kg"])
        self.assertIsNone(response.data["measurement"]["chest_cm"])
        self.assertEqual(response.data["measurement"]["measurement_notes"], "")

    def test_post_measurement_with_boundary_values(self):
        """Test POST with boundary (min/max) values"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "50.0",  # Minimum
            "weight_kg": "20.0",  # Minimum
            "chest_cm": "30.0",  # Minimum
            "shoulders_cm": "30.0",  # Minimum
            "biceps_left_cm": "10.0",  # Minimum
            "biceps_right_cm": "10.0",  # Minimum
            "waist_cm": "40.0",  # Minimum
        }
        response = self.client.post(self.create_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["measurement"]["height_cm"], "50.0")
        self.assertEqual(response.data["measurement"]["weight_kg"], "20.0")

        # Test maximum values
        data = {
            "height_cm": "300.0",  # Maximum
            "weight_kg": "500.0",  # Maximum
            "chest_cm": "200.0",  # Maximum
            "shoulders_cm": "200.0",  # Maximum
            "biceps_left_cm": "100.0",  # Maximum
            "biceps_right_cm": "100.0",  # Maximum
            "waist_cm": "250.0",  # Maximum
        }
        response = self.client.post(self.create_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["measurement"]["height_cm"], "300.0")
        self.assertEqual(response.data["measurement"]["weight_kg"], "500.0")

    def test_post_measurement_just_above_minimum_values(self):
        """Test POST with values just above minimum"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "50.1",
            "weight_kg": "20.1",
            "chest_cm": "30.1",
            "shoulders_cm": "30.1",
            "biceps_left_cm": "10.1",
            "biceps_right_cm": "10.1",
            "waist_cm": "40.1",
        }
        response = self.client.post(self.create_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_post_measurement_just_below_maximum_values(self):
        """Test POST with values just below maximum"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "299.9",
            "weight_kg": "499.9",
            "chest_cm": "199.9",
            "shoulders_cm": "199.9",
            "biceps_left_cm": "99.9",
            "biceps_right_cm": "99.9",
            "waist_cm": "249.9",
        }
        response = self.client.post(self.create_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_post_measurement_with_string_values(self):
        """Test POST with string values (should be handled by serializer)"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "abc",
            "weight_kg": "xyz",
        }
        response = self.client.post(self.create_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UserMeasurementDetailViewTest(TestCase):
    """Test suite for UserMeasurementDetailView"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number="09024698787",
            first_name="Test",
            last_name="User",
        )
        self.other_user = User.objects.create_user(
            phone_number="09876543210",
            first_name="Other",
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
            measurement_notes="Test measurement",
        )

        self.url = reverse(
            "user_measurements:detail", kwargs={"measurement_id": self.measurement.id}
        )
        self.delete_url = reverse(
            "user_measurements:delete", kwargs={"measurement_id": self.measurement.id}
        )
        self.update_url = reverse(
            "user_measurements:update", kwargs={"measurement_id": self.measurement.id}
        )

    def test_get_measurement_authenticated(self):
        """Test GET measurement with authenticated user"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("measurements", response.data)
        self.assertEqual(
            response.data["measurements"]["id"],
            str(self.measurement.id),
        )
        self.assertEqual(
            response.data["measurements"]["measurement_notes"],
            "Test measurement",
        )

    def test_get_measurement_unauthenticated(self):
        """Test GET measurement without authentication"""
        response = self.client.get(self.url)
        # The API returns 400 for unauthenticated requests
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

    def test_get_measurement_not_owner(self):
        """Test GET measurement that belongs to another user"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.MEASUREMENT_NOT_FOUND[0],
        )

    def test_get_measurement_not_found(self):
        """Test GET measurement with non-existent ID"""
        self.client.force_authenticate(user=self.user)
        non_existent_url = reverse(
            "user_measurements:detail",
            kwargs={"measurement_id": "00000000-0000-0000-0000-000000000000"},
        )
        response = self.client.get(non_existent_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.MEASUREMENT_NOT_FOUND[0],
        )

    def test_put_measurement_authenticated(self):
        """Test PUT (update) measurement with authenticated user"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "180.0",
            "weight_kg": "75.5",
            "chest_cm": "105.0",
            "measurement_notes": "Updated measurement",
        }

        response = self.client.put(self.update_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("measurement", response.data)
        self.assertEqual(response.data["measurement"]["height_cm"], "180.0")
        self.assertEqual(response.data["measurement"]["weight_kg"], "75.5")
        self.assertEqual(
            response.data["measurement"]["measurement_notes"],
            "Updated measurement",
        )

        # Verify database was updated
        self.measurement.refresh_from_db()
        self.assertEqual(self.measurement.height_cm, Decimal("180.0"))
        self.assertEqual(self.measurement.weight_kg, Decimal("75.5"))

    def test_put_measurement_unauthenticated(self):
        """Test PUT measurement without authentication"""
        data = {
            "height_cm": "180.0",
            "weight_kg": "75.5",
        }
        response = self.client.put(self.update_url, data, format="json")
        # The API returns 400 for unauthenticated requests
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

    def test_put_measurement_not_owner(self):
        """Test PUT measurement that belongs to another user"""
        self.client.force_authenticate(user=self.other_user)
        data = {
            "height_cm": "180.0",
            "weight_kg": "75.5",
        }

        response = self.client.put(self.update_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.MEASUREMENT_NOT_FOUND[0],
        )

    def test_put_measurement_partial_update(self):
        """Test PUT with partial update (using partial=True in view)"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "182.0",
            # weight_kg is not provided, should remain unchanged
        }

        response = self.client.put(self.update_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["measurement"]["height_cm"], "182.0")
        self.assertEqual(
            response.data["measurement"]["weight_kg"],
            "72.3",  # Unchanged
        )

        # Verify database
        self.measurement.refresh_from_db()
        self.assertEqual(self.measurement.height_cm, Decimal("182.0"))
        self.assertEqual(self.measurement.weight_kg, Decimal("72.3"))

    def test_put_measurement_invalid_data(self):
        """Test PUT measurement with invalid data"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": "45",  # Too low
            "weight_kg": "75.5",
        }

        response = self.client.put(self.update_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.INVALID_HEIGHT[0],
        )

    def test_delete_measurement_authenticated(self):
        """Test DELETE measurement with authenticated user"""
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.delete_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data)

        # Verify it was deleted from database
        with self.assertRaises(Measurements.DoesNotExist):
            Measurements.objects.get(id=self.measurement.id)

    def test_delete_measurement_unauthenticated(self):
        """Test DELETE measurement without authentication"""
        response = self.client.delete(self.delete_url)
        # The API returns 400 for unauthenticated requests
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

    def test_delete_measurement_not_owner(self):
        """Test DELETE measurement that belongs to another user"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.delete(self.delete_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.MEASUREMENT_NOT_FOUND[0],
        )

        # Verify it wasn't deleted
        self.assertTrue(Measurements.objects.filter(id=self.measurement.id).exists())

    def test_delete_measurement_not_found(self):
        """Test DELETE measurement with non-existent ID"""
        self.client.force_authenticate(user=self.user)
        delete_url = reverse(
            "user_measurements:delete",
            kwargs={"measurement_id": "00000000-0000-0000-0000-000000000000"},
        )
        response = self.client.delete(delete_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.MEASUREMENT_NOT_FOUND[0],
        )

    # ========== EDGE CASE TESTS ==========

    def test_put_measurement_with_empty_data(self):
        """Test PUT with empty data (partial update with empty data)"""
        self.client.force_authenticate(user=self.user)
        response = self.client.put(self.update_url, {}, format="json")
        # Since partial=True, empty data should be accepted
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_put_measurement_with_null_values(self):
        """Test PUT with null values for fields"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": None,
            "weight_kg": None,
            "chest_cm": None,
            "measurement_notes": "",
        }
        response = self.client.put(self.update_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["measurement"]["height_cm"])
        self.assertIsNone(response.data["measurement"]["weight_kg"])

    def test_get_measurements_after_delete(self):
        """Test getting measurements after deletion"""
        measurement = Measurements.objects.create(user=self.user)
        url = reverse(
            "user_measurements:detail", kwargs={"measurement_id": measurement.id}
        )
        delete_url = reverse(
            "user_measurements:delete", kwargs={"measurement_id": measurement.id}
        )

        # Delete the measurement
        self.client.force_authenticate(user=self.user)
        self.client.delete(delete_url)

        # Try to get it again
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.MEASUREMENT_NOT_FOUND[0],
        )

    def test_invalid_uuid_format(self):
        """Test accessing detail with invalid UUID format"""
        self.client.force_authenticate(user=self.user)
        # Use a valid UUID that doesn't exist, but with an invalid format we need to
        # construct the URL manually since reverse won't work with invalid UUID
        invalid_url = f"/api/measurements/invalid-uuid-format/"
        response = self.client.get(invalid_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_put_measurement_remove_all_fields(self):
        """Test PUT removing all fields (setting to None)"""
        self.client.force_authenticate(user=self.user)
        data = {
            "height_cm": None,
            "weight_kg": None,
            "chest_cm": None,
            "shoulders_cm": None,
            "biceps_left_cm": None,
            "biceps_right_cm": None,
            "forearms_left_cm": None,
            "forearms_right_cm": None,
            "waist_cm": None,
            "abdomen_cm": None,
            "hips_cm": None,
            "quadriceps_left_cm": None,
            "quadriceps_right_cm": None,
            "calves_left_cm": None,
            "calves_right_cm": None,
            "glutes_cm": None,
            "measurement_notes": "",
        }
        response = self.client.put(self.update_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify all fields are None
        self.measurement.refresh_from_db()
        self.assertIsNone(self.measurement.height_cm)
        self.assertIsNone(self.measurement.weight_kg)
        self.assertIsNone(self.measurement.chest_cm)
        self.assertEqual(self.measurement.measurement_notes, "")

    def test_delete_already_deleted_measurement(self):
        """Test deleting a measurement that's already deleted"""
        self.client.force_authenticate(user=self.user)
        # Delete once
        self.client.delete(self.delete_url)

        # Try to delete again
        response = self.client.delete(self.delete_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.MEASUREMENT_NOT_FOUND[0],
        )


class UserMeasurementsViewIntegrationTest(TestCase):
    """Integration tests for measurements views"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number="09024698787",
            first_name="Test",
            last_name="User",
        )
        self.client.force_authenticate(user=self.user)
        self.list_url = reverse("user_measurements:list")
        self.create_url = reverse("user_measurements:create")

    def test_full_crud_flow(self):
        """Test complete CRUD flow for measurements"""
        # 1. Create measurement
        create_data = {
            "height_cm": "175.0",
            "weight_kg": "70.0",
            "chest_cm": "100.0",
            "measurement_notes": "Initial measurement",
        }
        response = self.client.post(self.create_url, create_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        measurement_id = response.data["measurement"]["id"]

        # 2. List measurements
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["measurements"]), 1)
        self.assertEqual(
            response.data["measurements"][0]["measurement_notes"],
            "Initial measurement",
        )

        # 3. Get single measurement
        detail_url = reverse(
            "user_measurements:detail", kwargs={"measurement_id": measurement_id}
        )
        delete_url = reverse(
            "user_measurements:delete", kwargs={"measurement_id": measurement_id}
        )
        update_url = reverse(
            "user_measurements:update", kwargs={"measurement_id": measurement_id}
        )
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["measurements"]["measurement_notes"],
            "Initial measurement",
        )

        # 4. Update measurement
        update_data = {
            "height_cm": "180.0",
            "weight_kg": "75.0",
            "measurement_notes": "Updated measurement",
        }
        response = self.client.put(update_url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["measurement"]["measurement_notes"],
            "Updated measurement",
        )

        # 5. Delete measurement
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 6. Verify deletion
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_multiple_users_data_isolation(self):
        """Test that users can only access their own measurements"""
        # Create another user
        other_user = User.objects.create_user(
            phone_number="09876543210",
            first_name="Other",
            last_name="User",
            password="testpass123",
        )

        # Create measurement for other user
        other_measurement = Measurements.objects.create(
            user=other_user,
            height_cm=Decimal("190.0"),
            weight_kg=Decimal("85.0"),
            measurement_notes="Other user measurement",
        )

        # Current user should see empty list (paginated response)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["measurements"], [])

        # Current user should not be able to access other user's measurement
        other_url = reverse(
            "user_measurements:detail", kwargs={"measurement_id": other_measurement.id}
        )
        response = self.client.get(other_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Other user should be able to access their measurement
        self.client.force_authenticate(user=other_user)
        response = self.client.get(other_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["measurements"]["measurement_notes"],
            "Other user measurement",
        )

    def test_response_format(self):
        """Test response format consistency"""
        # Create measurement
        create_data = {
            "height_cm": "175.0",
            "weight_kg": "70.0",
        }
        response = self.client.post(self.create_url, create_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("measurement", response.data)

        # List measurements
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("measurements", response.data)
        self.assertIsInstance(response.data["measurements"], list)

        # Get single measurement
        measurement_id = Measurements.objects.filter(user=self.user).first().id
        detail_url = reverse(
            "user_measurements:detail", kwargs={"measurement_id": measurement_id}
        )
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("measurements", response.data)
        self.assertIsInstance(response.data["measurements"], dict)

    # ========== EDGE CASE TESTS ==========

    def test_create_and_update_same_measurement_multiple_times(self):
        """Test creating and updating the same measurement multiple times"""
        # Create measurement
        create_data = {
            "height_cm": "170.0",
            "weight_kg": "65.0",
            "measurement_notes": "First version",
        }
        response = self.client.post(self.create_url, create_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        measurement_id = response.data["measurement"]["id"]
        update_url = reverse(
            "user_measurements:update", kwargs={"measurement_id": measurement_id}
        )

        # Update multiple times
        for i in range(3):
            update_data = {
                "height_cm": str(170.0 + i),
                "weight_kg": str(65.0 + i),
                "measurement_notes": f"Version {i+2}",
            }
            response = self.client.put(update_url, update_data, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Verify update by fetching from database
            measurement = Measurements.objects.get(id=measurement_id)
            self.assertEqual(float(measurement.height_cm), 170.0 + i)

    def test_concurrent_operations(self):
        """Test concurrent operations on same measurement"""
        # Create measurement
        create_data = {
            "height_cm": "170.0",
            "weight_kg": "65.0",
        }

        response = self.client.post(self.create_url, create_data, format="json")
        measurement_id = response.data["measurement"]["id"]
        delete_url = reverse(
            "user_measurements:delete", kwargs={"measurement_id": measurement_id}
        )
        update_url = reverse(
            "user_measurements:update", kwargs={"measurement_id": measurement_id}
        )

        # Update and delete in sequence
        update_data = {"height_cm": "180.0"}
        response = self.client.put(update_url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Try to update after delete
        response = self.client.put(update_url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MeasurementPhotosViewTest(TestCase):
    """Test suite for MeasurementPhotosView"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number="09024698787",
            first_name="Test",
            last_name="User",
        )
        self.other_user = User.objects.create_user(
            phone_number="09876543210",
            first_name="Other",
            last_name="User",
        )

        self.measurement = Measurements.objects.create(
            user=self.user,
            height_cm=Decimal("175.5"),
            weight_kg=Decimal("72.3"),
            measurement_notes="Test measurement",
        )

        self.photos_url = reverse(
            "user_measurements:photos-list",
            kwargs={"measurement_id": self.measurement.id},
        )
        self.photo_create_url = reverse(
            "user_measurements:photo-create",
            kwargs={"measurement_id": self.measurement.id},
        )

        # Create test image
        self.test_image = self.create_test_image()

    def create_test_image(self, format="JPEG"):
        """Create a test image"""
        image = Image.new("RGB", (100, 100), color="red")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format=format)
        image_bytes.seek(0)

        ext = "jpg" if format == "JPEG" else format.lower()
        return SimpleUploadedFile(
            f"test.{ext}", image_bytes.read(), content_type=f"image/{ext}"
        )

    def test_get_photos_authenticated(self):
        """Test GET photos with authenticated user"""
        # Create some photos
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

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.photos_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("photos", response.data)
        self.assertEqual(len(response.data["photos"]), 2)

        # Check that photos are ordered by created_at desc
        self.assertEqual(response.data["photos"][0]["type"], "BACK")
        self.assertEqual(response.data["photos"][1]["type"], "FRONT")

    def test_get_photos_unauthenticated(self):
        """Test GET photos without authentication"""
        response = self.client.get(self.photos_url)
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

    def test_get_photos_no_photos(self):
        """Test GET photos when measurement has no photos"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.photos_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.NO_EXISTING_MEASUREMENTS_PHOTOS[0],
        )

    def test_get_photos_not_owner(self):
        """Test GET photos for measurement owned by another user"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.photos_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.NO_EXISTING_MEASUREMENTS_PHOTOS[0],
        )

    def test_post_photo_authenticated(self):
        """Test POST photo with authenticated user"""
        self.client.force_authenticate(user=self.user)
        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": self.test_image,
        }

        response = self.client.post(self.photo_create_url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("photo", response.data)
        self.assertEqual(response.data["photo"]["type"], "FRONT")
        self.assertTrue(response.data["photo"]["photo"].endswith(".webp"))

        # Verify it was saved
        self.assertEqual(
            MeasurementPhotos.objects.filter(measurements=self.measurement).count(), 1
        )

    def test_post_photo_rejects_missing_null_and_empty_uploads(self):
        self.client.force_authenticate(user=self.user)
        cases = (
            ({"photo": None}, "json", MeasurementsError.PHOTO_FILE_REQUIRED[0]),
            ({}, "json", MeasurementsError.PHOTO_FILE_REQUIRED[0]),
            ({"photo": ""}, "json", "VALIDATION_ERROR"),
            (
                {
                    "photo": SimpleUploadedFile(
                        "empty.jpg", b"", content_type="image/jpeg"
                    )
                },
                "multipart",
                "VALIDATION_ERROR",
            ),
        )
        for photo_data, request_format, error_code in cases:
            with self.subTest(photo_data=photo_data):
                response = self.client.post(
                    self.photo_create_url,
                    {"type": MeasurementPhotos.PhotoType.FRONT, **photo_data},
                    format=request_format,
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                payload = response.json()
                self.assertFalse(payload["success"])
                self.assertIsNone(payload["data"])
                self.assertEqual(payload["error_code"], error_code)
                self.assertFalse(MeasurementPhotos.objects.exists())

    def test_post_photo_unauthenticated(self):
        """Test POST photo without authentication"""
        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": self.test_image,
        }
        response = self.client.post(self.photo_create_url, data, format="multipart")
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

    def test_post_photo_not_owner(self):
        """Test POST photo for measurement owned by another user"""
        self.client.force_authenticate(user=self.other_user)
        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": self.test_image,
        }
        response = self.client.post(self.photo_create_url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_duplicate_photo_type(self):
        """Test POST photo with duplicate type"""
        # Create first photo
        MeasurementPhotos.objects.create(
            measurements=self.measurement,
            type=MeasurementPhotos.PhotoType.FRONT,
            photo=self.test_image,
        )

        self.client.force_authenticate(user=self.user)
        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": self.create_test_image(),
        }
        response = self.client.post(self.photo_create_url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            MeasurementsError.MEASUREMENTS_PHOTO_TYPE_EXIST[0],
        )

    def test_post_photo_invalid_type(self):
        """Test POST photo with invalid type"""
        self.client.force_authenticate(user=self.user)
        data = {
            "type": "INVALID",
            "photo": self.test_image,
        }
        response = self.client.post(self.photo_create_url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"],
            "VALIDATION_ERROR",
        )


class MeasurementPhotoDetailViewTest(TestCase):
    """Test suite for MeasurementPhotoDetailView"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number="09024698787",
            first_name="Test",
            last_name="User",
        )
        self.other_user = User.objects.create_user(
            phone_number="09876543210",
            first_name="Other",
            last_name="User",
        )

        self.measurement = Measurements.objects.create(
            user=self.user,
            height_cm=Decimal("175.5"),
            weight_kg=Decimal("72.3"),
            measurement_notes="Test measurement",
        )

        # Create test image
        self.test_image = self.create_test_image()

        # Create a photo
        self.photo = MeasurementPhotos.objects.create(
            measurements=self.measurement,
            type=MeasurementPhotos.PhotoType.FRONT,
            photo=self.test_image,
        )

        self.detail_url = reverse(
            "user_measurements:photo-detail",
            kwargs={"measurement_id": self.measurement.id, "photo_id": self.photo.id},
        )
        self.photo_delete_url = reverse(
            "user_measurements:photo-delete",
            kwargs={"measurement_id": self.measurement.id, "photo_id": self.photo.id},
        )

    def create_test_image(self):
        """Create a test image"""
        image = Image.new("RGB", (100, 100), color="red")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="JPEG")
        image_bytes.seek(0)
        return SimpleUploadedFile(
            "test.jpg", image_bytes.read(), content_type="image/jpeg"
        )

    def test_action_routes_require_active_user(self):
        measurement_kwargs = {"measurement_id": self.measurement.id}
        photo_kwargs = {**measurement_kwargs, "photo_id": self.photo.id}
        routes = [
            ("create", {}, "post"),
            ("update", measurement_kwargs, "put"),
            ("delete", measurement_kwargs, "delete"),
            ("photo-create", measurement_kwargs, "post"),
            ("photo-delete", photo_kwargs, "delete"),
        ]
        for user, expected_status in [
            (None, status.HTTP_400_BAD_REQUEST),
            (self.user, status.HTTP_404_NOT_FOUND),
        ]:
            self.user.is_active = False
            self.user.save()
            self.client.force_authenticate(user=user)
            for name, kwargs, method in routes:
                with self.subTest(route=name, authenticated=user is not None):
                    url = reverse(f"user_measurements:{name}", kwargs=kwargs)
                    response = getattr(self.client, method)(url, {}, format="json")
                    self.assertEqual(response.status_code, expected_status)
        self.assertEqual(Measurements.objects.filter(user=self.user).count(), 1)
        self.assertTrue(MeasurementPhotos.objects.filter(pk=self.photo.pk).exists())

    def test_get_photo_authenticated(self):
        """Test GET photo with authenticated user"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("photo", response.data)
        self.assertEqual(response.data["photo"]["id"], str(self.photo.id))
        self.assertEqual(response.data["photo"]["type"], "FRONT")

    def test_get_photo_unauthenticated(self):
        """Test GET photo without authentication"""
        response = self.client.get(self.detail_url)
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

    def test_get_photo_not_owner(self):
        """Test GET photo owned by another user"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"], MeasurementsError.PHOTO_NOT_FOUND[0]
        )

    def test_get_photo_not_found(self):
        """Test GET photo with non-existent ID"""
        self.client.force_authenticate(user=self.user)
        invalid_url = reverse(
            "user_measurements:photo-detail",
            kwargs={
                "measurement_id": self.measurement.id,
                "photo_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        response = self.client.get(invalid_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"], MeasurementsError.PHOTO_NOT_FOUND[0]
        )

    def test_delete_photo_authenticated(self):
        """Test DELETE photo with authenticated user"""
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.photo_delete_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify it was deleted
        with self.assertRaises(MeasurementPhotos.DoesNotExist):
            MeasurementPhotos.objects.get(id=self.photo.id)

    def test_delete_photo_unauthenticated(self):
        """Test DELETE photo without authentication"""
        response = self.client.delete(self.photo_delete_url)
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

    def test_delete_photo_not_owner(self):
        """Test DELETE photo owned by another user"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.delete(self.photo_delete_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"], MeasurementsError.PHOTO_NOT_FOUND[0]
        )

    def test_delete_photo_not_found(self):
        """Test DELETE photo with non-existent ID"""
        self.client.force_authenticate(user=self.user)
        photo_delete_url = reverse(
            "user_measurements:photo-delete",
            kwargs={
                "measurement_id": self.measurement.id,
                "photo_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        response = self.client.delete(photo_delete_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"], MeasurementsError.PHOTO_NOT_FOUND[0]
        )

    def test_delete_photo_file_cleanup(self):
        """Test that photo file is deleted from storage"""
        self.client.force_authenticate(user=self.user)

        # Get the file path
        file_path = self.photo.photo.path

        # Verify file exists
        self.assertTrue(default_storage.exists(file_path))

        # Delete the photo
        self.client.delete(self.photo_delete_url)

        # Verify file is deleted
        self.assertFalse(default_storage.exists(file_path))

    def test_get_photo_after_deletion(self):
        """Test getting a photo after it's deleted"""
        self.client.force_authenticate(user=self.user)

        # Delete the photo
        self.client.delete(self.photo_delete_url)

        # Try to get it again
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_code", response.data)
        self.assertEqual(
            response.data["error_code"], MeasurementsError.PHOTO_NOT_FOUND[0]
        )


class MeasurementPhotosIntegrationTest(TestCase):
    """Integration tests for measurement photos"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number="09024698787",
            first_name="Test",
            last_name="User",
        )
        self.client.force_authenticate(user=self.user)

        self.measurement = Measurements.objects.create(
            user=self.user,
            height_cm=Decimal("175.5"),
            weight_kg=Decimal("72.3"),
        )

        self.photos_url = reverse(
            "user_measurements:photos-list",
            kwargs={"measurement_id": self.measurement.id},
        )
        self.photo_create_url = reverse(
            "user_measurements:photo-create",
            kwargs={"measurement_id": self.measurement.id},
        )

    def create_test_image(self, format="JPEG"):
        """Create a test image"""
        image = Image.new("RGB", (100, 100), color="red")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format=format)
        image_bytes.seek(0)

        ext = "jpg" if format == "JPEG" else format.lower()
        return SimpleUploadedFile(
            f"test.{ext}", image_bytes.read(), content_type=f"image/{ext}"
        )

    def test_full_photo_crud_flow(self):
        """Test complete CRUD flow for photos"""
        # 1. Create photo
        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": self.create_test_image(),
        }
        response = self.client.post(self.photo_create_url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        photo_id = response.data["photo"]["id"]

        # 2. List photos
        response = self.client.get(self.photos_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["photos"]), 1)
        self.assertEqual(response.data["photos"][0]["type"], "FRONT")

        # 3. Get single photo
        detail_url = reverse(
            "user_measurements:photo-detail",
            kwargs={"measurement_id": self.measurement.id, "photo_id": photo_id},
        )
        photo_delete_url = reverse(
            "user_measurements:photo-delete",
            kwargs={"measurement_id": self.measurement.id, "photo_id": photo_id},
        )
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["photo"]["id"], photo_id)

        # 4. Delete photo
        response = self.client.delete(photo_delete_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 5. Verify deletion
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_multiple_photo_types(self):
        """Test creating multiple photos with different types"""
        # Create front photo
        data1 = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": self.create_test_image(),
        }
        response = self.client.post(self.photo_create_url, data1, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Create back photo
        data2 = {
            "type": MeasurementPhotos.PhotoType.BACK,
            "photo": self.create_test_image(),
        }
        response = self.client.post(self.photo_create_url, data2, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Create side photo
        data3 = {
            "type": MeasurementPhotos.PhotoType.SIDE,
            "photo": self.create_test_image(),
        }
        response = self.client.post(self.photo_create_url, data3, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify all three exist
        response = self.client.get(self.photos_url)
        self.assertEqual(len(response.data["photos"]), 3)

        types = [p["type"] for p in response.data["photos"]]
        self.assertIn("FRONT", types)
        self.assertIn("BACK", types)
        self.assertIn("SIDE", types)

    def test_delete_measurement_cascades_to_photos(self):
        """Test that deleting measurement also deletes its photos"""
        # Create a photo
        data = {
            "type": MeasurementPhotos.PhotoType.FRONT,
            "photo": self.create_test_image(),
        }
        response = self.client.post(self.photo_create_url, data, format="multipart")
        photo_id = response.data["photo"]["id"]

        # Delete the measurement
        delete_url = reverse(
            "user_measurements:delete", kwargs={"measurement_id": self.measurement.id}
        )
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify photo is deleted
        with self.assertRaises(MeasurementPhotos.DoesNotExist):
            MeasurementPhotos.objects.get(id=photo_id)
