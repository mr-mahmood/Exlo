# user_referrals/tests/test_views.py
# type: ignore

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from django.conf import settings
from django.db import IntegrityError, transaction
from users.models import User
from users_referrals.models import Referral
from core.errors import ReferralError, APIError, UserAccountError, AuthenticationError
from django.conf import settings


class UserReferralPIViewTest(TestCase):
    """Test user referral management views"""

    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()

        # Create main user (referrer)
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )

        # Create another user for permission tests
        self.other_user = User.objects.create_user(
            phone_number="09987654321",
            first_name="Jane",
            last_name="Smith",
            gender=User.Gender.FEMALE,
        )

        # Create referred users
        self.referred_user1 = User.objects.create_user(
            phone_number="09111111111",
            first_name="Alice",
            last_name="Johnson",
            gender=User.Gender.FEMALE,
        )

        self.referred_user2 = User.objects.create_user(
            phone_number="09222222222",
            first_name="Bob",
            last_name="Williams",
            gender=User.Gender.MALE,
        )

        self.referred_user3 = User.objects.create_user(
            phone_number="09333333333",
            first_name="Charlie",
            last_name="Brown",
            gender=User.Gender.MALE,
        )

        # Create referrals for the user
        self.referral1 = Referral.objects.create(
            referrer=self.user,
            referred_user=self.referred_user1,
            referred_at=timezone.now(),
        )

        self.referral2 = Referral.objects.create(
            referrer=self.user,
            referred_user=self.referred_user2,
            referred_at=timezone.now(),
        )

        # Create a referral for another user (should not be visible)
        self.other_referral = Referral.objects.create(
            referrer=self.other_user,
            referred_user=self.referred_user3,
            referred_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse("user_referrals:user-referrals")

    # ========== GET TESTS ==========

    def test_get_referrals_success(self):
        """Test retrieving user referrals successfully"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check that referrals key exists and has correct data
        self.assertIn("referrals", response.data)  # type: ignore
        self.assertEqual(len(response.data["referrals"]), 2)  # type: ignore

        # Verify pagination fields
        self.assertIn("next", response.data)  # type: ignore
        self.assertIn("previous", response.data)  # type: ignore

        # Verify referral data contains expected fields
        referral_data = response.data["referrals"][0]  # type: ignore
        self.assertIn("referred_user", referral_data)
        self.assertIn("referred_at", referral_data)

        # Verify nested user data
        referred_user_data = referral_data["referred_user"]
        expected_fields = ["phone_number", "first_name", "last_name"]
        for field in expected_fields:
            self.assertIn(field, referred_user_data)

        # Verify all referrals belong to the user
        for referral in response.data["referrals"]:
            phone = referral["referred_user"]["phone_number"]
            self.assertIn(phone, ["09111111111", "09222222222"])

    def test_get_referrals_no_referrals(self):
        """Test retrieving referrals when user has no referrals"""
        # Create a new user with no referrals
        new_user = User.objects.create_user(
            phone_number="09444444444",
            first_name="No",
            last_name="Referrals",
            gender=User.Gender.MALE,
        )

        self.client.force_authenticate(user=new_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["referrals"], [])
        self.assertIsNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_get_referrals_unauthenticated(self):
        """Test retrieving referrals without authentication"""
        client = APIClient()
        response = client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # type: ignore
        self.assertEqual(response.data["error"], AuthenticationError.TOKEN_NOT_PROVIDE[0])  # type: ignore

    def test_get_referrals_blocked_user(self):
        """Test retrieving referrals for blocked user"""
        self.user.is_blocked = True
        self.user.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_referrals_inactive_user(self):
        """Test retrieving referrals for inactive user"""
        self.user.is_active = False
        self.user.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_referrals_does_not_show_other_users_referrals(self):
        """Test that user cannot see other users' referrals"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["referrals"]), 2)  # type: ignore

        # Verify the other user's referral is not included
        for referral in response.data["referrals"]:  # type: ignore
            referred_phone = referral["referred_user"]["phone_number"]
            self.assertNotEqual(referred_phone, "09333333333")

    def test_get_referrals_select_related_optimization(self):
        """Test that select_related is used to prevent N+1 queries"""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Count the number of queries
        # With pagination, we expect: 1 for count + 1 for data = 2-3 queries
        query_count = len(queries)
        # The pagination adds a count query, so we allow up to 3 queries
        self.assertLessEqual(query_count, 3, f"Expected 2-3 queries, got {query_count}")

    # ========== RESPONSE FORMAT TESTS ==========

    def test_get_referrals_response_format(self):
        """Test that GET response has correct format"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("referrals", response.data)  # type: ignore
        self.assertIsInstance(response.data["referrals"], list)  # type: ignore

        # Check pagination fields
        self.assertIn("next", response.data)  # type: ignore
        self.assertIn("previous", response.data)  # type: ignore

        if len(response.data["referrals"]) > 0:  # type: ignore
            referral = response.data["referrals"][0]  # type: ignore
            self.assertIn("referred_user", referral)
            self.assertIn("referred_at", referral)

            # Verify nested user data
            referred_user = referral["referred_user"]
            self.assertIsInstance(referred_user["phone_number"], str)
            self.assertIsInstance(referred_user["first_name"], str)
            self.assertIsInstance(referred_user["last_name"], str)

    def test_get_referrals_serializer_fields(self):
        """Test that serializer returns only expected fields"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        referral = response.data["referrals"][0]  # type: ignore

        # Should NOT include referrer info
        self.assertNotIn("referrer", referral)
        self.assertNotIn("id", referral)
        self.assertNotIn("created_at", referral)
        self.assertNotIn("updated_at", referral)

        # Should include only referred_user and referred_at
        self.assertIn("referred_user", referral)
        self.assertIn("referred_at", referral)

        # Nested user should NOT include sensitive fields
        referred_user = referral["referred_user"]
        self.assertNotIn("password", referred_user)
        self.assertNotIn("is_active", referred_user)
        self.assertNotIn("is_blocked", referred_user)
        self.assertNotIn("is_superuser", referred_user)
        self.assertNotIn("last_login", referred_user)
        self.assertNotIn("created_at", referred_user)
        self.assertNotIn("updated_at", referred_user)

    # ========== EDGE CASES ==========

    def test_get_referrals_many_referrals(self):
        """Test retrieving many referrals"""
        # Create many referrals
        for i in range(10):
            referred_user = User.objects.create_user(
                phone_number=f"099999999{i:02d}",
                first_name=f"User{i}",
                last_name="Test",
                gender=User.Gender.MALE,
            )
            Referral.objects.create(
                referrer=self.user,
                referred_user=referred_user,
                referred_at=timezone.now(),
            )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["referrals"]), 12)  # type: ignore

    def test_get_referrals_ordering(self):
        """Test that referrals are ordered by created_at desc"""
        # Create a newer referral
        import time

        time.sleep(0.1)

        newer_user = User.objects.create_user(
            phone_number="09555555555",
            first_name="Newer",
            last_name="User",
            gender=User.Gender.MALE,
        )
        newer_referral = Referral.objects.create(
            referrer=self.user,
            referred_user=newer_user,
            referred_at=timezone.now(),
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Most recent should be first
        first_referral = response.data["referrals"][0]  # type: ignore
        self.assertEqual(first_referral["referred_user"]["phone_number"], "09555555555")

    def test_get_referrals_with_deleted_user(self):
        """Test behavior when referred user is deleted (should not happen due to CASCADE)"""
        referred_user = User.objects.create_user(
            phone_number="09666666666",
            first_name="Delete",
            last_name="Me",
            gender=User.Gender.MALE,
        )
        referral = Referral.objects.create(
            referrer=self.user,
            referred_user=referred_user,
            referred_at=timezone.now(),
        )

        # Delete the referred user
        referred_user.delete()

        # The referral should be automatically deleted due to CASCADE
        self.assertFalse(Referral.objects.filter(id=referral.id).exists())

        # Get referrals should not include the deleted one
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["referrals"]), 2)  # type: ignore

    # ========== PERFORMANCE TESTS ==========

    def test_get_referrals_query_count(self):
        """Test that only 2-3 queries are executed (no N+1)"""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # Create more referrals to test N+1
        for i in range(20):
            referred_user = User.objects.create_user(
                phone_number=f"097777777{i:02d}",
                first_name=f"Perf{i}",
                last_name="Test",
                gender=User.Gender.MALE,
            )
            Referral.objects.create(
                referrer=self.user,
                referred_user=referred_user,
                referred_at=timezone.now(),
            )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["referrals"]), 22)  # type: ignore

        # With pagination, we expect: 1 for count + 1 for data = 2-3 queries
        # The third query might be for pagination or session validation
        query_count = len(queries)
        self.assertLessEqual(
            query_count,
            3,
            f"Expected 2-3 queries, got {query_count}. N+1 problem detected!",
        )

    # ========== DATA CONSISTENCY TESTS ==========

    def test_get_referrals_duplicate_referral_prevention(self):
        """Test that duplicate referrals are prevented (unique_together)"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Referral.objects.create(
                    referrer=self.user,
                    referred_user=self.referred_user1,  # Already exists
                    referred_at=timezone.now(),
                )

        # Should still have only 2 referrals
        self.assertEqual(Referral.objects.filter(referrer=self.user).count(), 2)

    def test_get_referrals_self_referral_prevention(self):
        """Test that self-referral is prevented"""
        # Self-referral should raise APIError
        with self.assertRaises(APIError) as context:
            Referral.objects.create(
                referrer=self.user,
                referred_user=self.user,  # Self referral
                referred_at=timezone.now(),
            )

        # Verify the error code
        self.assertEqual(
            context.exception.error_code, ReferralError.SELF_REFERRAL_NOT_ALLOWED[0]
        )

        # Verify no self-referral was created
        self.assertEqual(Referral.objects.filter(referrer=self.user).count(), 2)

    def test_referral_str_method(self):
        """Test the string representation of Referral model"""
        new_user = User.objects.create_user(
            phone_number="09888888888",
            first_name="Test",
            last_name="User",
            gender=User.Gender.MALE,
        )
        referral = Referral.objects.create(
            referrer=self.user,
            referred_user=new_user,
            referred_at=timezone.now(),
        )
        expected_str = f"{new_user} referred by {self.user}"
        self.assertEqual(str(referral), expected_str)

    # ========== PAGINATION TESTS ==========

    def test_pagination_default_page_size(self):
        """Test that pagination uses default page size of 50"""
        # Create 55 referrals to test pagination
        for i in range(55):
            referred_user = User.objects.create_user(
                phone_number=f"099999999{i:02d}",
                first_name=f"User{i}",
                last_name="Test",
                gender=User.Gender.MALE,
            )
            Referral.objects.create(
                referrer=self.user,
                referred_user=referred_user,
                referred_at=timezone.now(),
            )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["referrals"]), 50)  # type: ignore
        self.assertIsNotNone(response.data["next"])  # type: ignore
        self.assertIsNone(response.data["previous"])  # type: ignore

    def test_pagination_custom_page_size(self):
        """Test that pagination respects custom page_size parameter"""
        # Create 30 referrals
        for i in range(30):
            referred_user = User.objects.create_user(
                phone_number=f"099999999{i:02d}",
                first_name=f"User{i}",
                last_name="Test",
                gender=User.Gender.MALE,
            )
            Referral.objects.create(
                referrer=self.user,
                referred_user=referred_user,
                referred_at=timezone.now(),
            )

        response = self.client.get(self.url, {"page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["referrals"]), 10)  # type: ignore
        self.assertIsNotNone(response.data["next"])  # type: ignore
        self.assertIsNone(response.data["previous"])  # type: ignore

    def test_pagination_max_page_size(self):
        """Test that pagination respects max_page_size limit of 100"""
        # Create 150 referrals
        for i in range(150):
            referred_user = User.objects.create_user(
                phone_number=f"099999999{i:02d}",
                first_name=f"User{i}",
                last_name="Test",
                gender=User.Gender.MALE,
            )
            Referral.objects.create(
                referrer=self.user,
                referred_user=referred_user,
                referred_at=timezone.now(),
            )

        response = self.client.get(self.url, {"page_size": 200})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return max_page_size (100) instead of requested 200
        self.assertEqual(len(response.data["referrals"]), 100)  # type: ignore

    def test_pagination_second_page(self):
        """Test that pagination works for second page"""
        # Create 55 referrals
        for i in range(55):
            referred_user = User.objects.create_user(
                phone_number=f"099999999{i:02d}",
                first_name=f"User{i}",
                last_name="Test",
                gender=User.Gender.MALE,
            )
            Referral.objects.create(
                referrer=self.user,
                referred_user=referred_user,
                referred_at=timezone.now(),
            )

        response = self.client.get(self.url, {"page": 2, "page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["referrals"]), 10)  # type: ignore
        # Should have next and previous links
        self.assertIsNotNone(response.data["next"])  # type: ignore
        self.assertIsNotNone(response.data["previous"])  # type: ignore

    def test_pagination_invalid_page(self):
        """Test that pagination handles invalid page number gracefully"""
        # Create 10 referrals
        for i in range(10):
            referred_user = User.objects.create_user(
                phone_number=f"099999999{i:02d}",
                first_name=f"User{i}",
                last_name="Test",
                gender=User.Gender.MALE,
            )
            Referral.objects.create(
                referrer=self.user,
                referred_user=referred_user,
                referred_at=timezone.now(),
            )

        response = self.client.get(self.url, {"page": 999})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pagination_with_referrals_less_than_page_size(self):
        """Test pagination when total referrals are less than page size"""
        # Only 2 referrals from setUp
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["referrals"]), 2)  # type: ignore
        self.assertIsNone(response.data["next"])  # type: ignore
        self.assertIsNone(response.data["previous"])  # type: ignore

    def test_pagination_response_structure(self):
        """Test that pagination response has all required fields"""
        # Create 25 referrals
        for i in range(25):
            referred_user = User.objects.create_user(
                phone_number=f"099999999{i:02d}",
                first_name=f"User{i}",
                last_name="Test",
                gender=User.Gender.MALE,
            )
            Referral.objects.create(
                referrer=self.user,
                referred_user=referred_user,
                referred_at=timezone.now(),
            )

        response = self.client.get(self.url, {"page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify response structure
        self.assertIn("next", response.data)  # type: ignore
        self.assertIn("previous", response.data)  # type: ignore
        self.assertIn("referrals", response.data)  # type: ignore

        # Verify referrals is a list
        self.assertIsInstance(response.data["referrals"], list)  # type: ignore
        self.assertEqual(len(response.data["referrals"]), 10)  # type: ignore

        # Verify each referral has required fields
        for referral in response.data["referrals"]:  # type: ignore
            self.assertIn("referred_user", referral)
            self.assertIn("referred_at", referral)
            # Verify nested user has required fields
            referred_user = referral["referred_user"]
            self.assertIn("phone_number", referred_user)
            self.assertIn("first_name", referred_user)
            self.assertIn("last_name", referred_user)


class UserReferralPIViewIntegrationTest(TestCase):
    """Integration tests for UserReferralPIView with actual URL routing"""

    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()

        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )

        self.referred_user = User.objects.create_user(
            phone_number="09111111111",
            first_name="Alice",
            last_name="Johnson",
            gender=User.Gender.FEMALE,
        )

        self.referral = Referral.objects.create(
            referrer=self.user,
            referred_user=self.referred_user,
            referred_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse("user_referrals:user-referrals")

    def test_get_referrals_endpoint_success(self):
        """Test the GET /api/referrals/ endpoint"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check the paginated response structure
        self.assertIn("next", response.data)  # type: ignore
        self.assertIn("previous", response.data)  # type: ignore
        self.assertIn("referrals", response.data)  # type: ignore
        self.assertEqual(len(response.data["referrals"]), 1)  # type: ignore

        referral = response.data["referrals"][0]  # type: ignore
        self.assertEqual(referral["referred_user"]["phone_number"], "09111111111")
        self.assertEqual(referral["referred_user"]["first_name"], "Alice")
        self.assertEqual(referral["referred_user"]["last_name"], "Johnson")

    def test_get_referrals_endpoint_unauthenticated(self):
        """Test the GET endpoint without authentication"""
        client = APIClient()
        response = client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # type: ignore
        self.assertEqual(response.data["error"], AuthenticationError.TOKEN_NOT_PROVIDE[0])  # type: ignore
