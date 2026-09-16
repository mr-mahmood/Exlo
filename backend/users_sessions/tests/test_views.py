# user_sessions/tests/test_views.py
# type: ignore

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
import uuid
from django.utils import timezone
from django.conf import settings
from users.models import User
from users_sessions.models import Session
from core.errors import SessionError, AuthenticationError


class UserSessionPIViewTest(TestCase):
    """Test user session management views"""

    def setUp(self):
        settings.DEBUG = True
        self.client = APIClient()

        # Create main user
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

        self.client.force_authenticate(user=self.user)
        self.url = reverse("user_sessions:user-sessions")

        # Create test sessions
        self.session1 = Session.objects.create(
            user=self.user,
            session_id=uuid.uuid4(),
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            last_activity_at=timezone.now(),
        )
        self.session2 = Session.objects.create(
            user=self.user,
            session_id=uuid.uuid4(),
            ip_address="192.168.1.2",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            last_activity_at=timezone.now(),
        )

    # ========== GET TESTS ==========

    def test_get_sessions_success(self):
        """Test retrieving user sessions successfully"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("sessions", response.data)  # type: ignore
        self.assertEqual(len(response.data["sessions"]), 2)  # type: ignore

        # Verify pagination fields
        self.assertIn("next", response.data)  # type: ignore
        self.assertIn("previous", response.data)  # type: ignore

        # Verify session data contains expected fields
        session_data = response.data["sessions"][0]  # type: ignore
        expected_fields = ["session_id", "ip_address", "user_agent", "last_activity_at"]
        for field in expected_fields:
            self.assertIn(field, session_data)

        # Verify all sessions belong to the user
        for session in response.data["sessions"]:  # type: ignore
            session_obj = Session.objects.get(session_id=session["session_id"])
            self.assertEqual(session_obj.user, self.user)

    def test_get_sessions_no_sessions(self):
        """Test retrieving sessions when user has no active sessions"""
        # Create a new user with no sessions
        new_user = User.objects.create_user(
            phone_number="09111111111",
            first_name="No",
            last_name="Sessions",
            gender=User.Gender.MALE,
        )

        # Use self.client (not a new client) and authenticate with new_user
        self.client.force_authenticate(user=new_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["sessions"], [])
        self.assertIsNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_get_sessions_unauthenticated(self):
        """Test retrieving sessions without authentication"""
        client = APIClient()
        response = client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # type: ignore
        self.assertEqual(response.data["error_code"], AuthenticationError.TOKEN_NOT_PROVIDE[0])  # type: ignore

    def test_get_sessions_inactive_user(self):
        """Test retrieving sessions for inactive user"""
        self.user.is_active = False
        self.user.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ========== DELETE TESTS ==========

    def test_delete_session_success(self):
        """Test deleting a session successfully"""
        session_id = str(self.session1.session_id)

        response = self.client.delete(
            self.url, data={"session_id": session_id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify session was deleted
        self.assertFalse(
            Session.objects.filter(
                user=self.user, session_id=self.session1.session_id
            ).exists()
        )

        # Verify other session still exists
        self.assertTrue(
            Session.objects.filter(
                user=self.user, session_id=self.session2.session_id
            ).exists()
        )

    def test_delete_session_not_found(self):
        """Test deleting a non-existent session"""
        non_existent_session_id = uuid.uuid4()

        response = self.client.delete(
            self.url, data={"session_id": str(non_existent_session_id)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], SessionError.SESSION_NOT_FOUND[0])  # type: ignore

    def test_delete_session_other_users_session(self):
        """Test that user cannot delete another user's session"""
        other_session = Session.objects.create(
            user=self.other_user,
            session_id=uuid.uuid4(),
            ip_address="192.168.1.3",
            user_agent="Mozilla/5.0",
            last_activity_at=timezone.now(),
        )

        response = self.client.delete(
            self.url, data={"session_id": str(other_session.session_id)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], SessionError.SESSION_NOT_FOUND[0])  # type: ignore

        # Verify session still exists
        self.assertTrue(
            Session.objects.filter(
                user=self.other_user, session_id=other_session.session_id
            ).exists()
        )

    def test_delete_session_missing_session_id(self):
        """Test deleting a session without providing session_id"""
        response = self.client.delete(self.url, data={}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], SessionError.SESSION_NOT_FOUND[0])  # type: ignore

    def test_delete_session_invalid_uuid(self):
        """Test deleting a session with invalid UUID format"""
        response = self.client.delete(
            self.url, data={"session_id": "invalid-uuid-format"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], SessionError.SESSION_NOT_FOUND[0])  # type: ignore

    def test_delete_session_unauthenticated(self):
        """Test deleting a session without authentication"""
        client = APIClient()
        response = client.delete(
            self.url, data={"session_id": str(self.session1.session_id)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # type: ignore
        self.assertEqual(response.data["error_code"], AuthenticationError.TOKEN_NOT_PROVIDE[0])  # type: ignore

    def test_delete_session_inactive_user(self):
        """Test deleting session for inactive user"""
        self.user.is_active = False
        self.user.save()

        response = self.client.delete(
            self.url, data={"session_id": str(self.session1.session_id)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], "NOT_FOUND")  # type: ignore

    # ========== BULK OPERATIONS ==========

    def test_delete_multiple_sessions(self):
        """Test deleting multiple sessions sequentially"""
        session_ids = [str(self.session1.session_id), str(self.session2.session_id)]

        for session_id in session_ids:
            response = self.client.delete(
                self.url, data={"session_id": session_id}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify all sessions are deleted
        self.assertEqual(Session.objects.filter(user=self.user).count(), 0)

    def test_delete_current_session(self):
        """Test deleting current active session"""
        current_session = Session.objects.create(
            user=self.user,
            session_id=uuid.uuid4(),
            ip_address="192.168.1.4",
            user_agent="Current Session",
            last_activity_at=timezone.now(),
        )

        response = self.client.delete(
            self.url,
            data={"session_id": str(current_session.session_id)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify session is deleted
        self.assertFalse(
            Session.objects.filter(
                user=self.user, session_id=current_session.session_id
            ).exists()
        )

    # ========== RESPONSE FORMAT TESTS ==========

    def test_get_sessions_response_format(self):
        """Test that GET response has correct format"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("sessions", response.data)  # type: ignore
        self.assertIsInstance(response.data["sessions"], list)  # type: ignore

        # Check pagination fields
        self.assertIn("next", response.data)  # type: ignore
        self.assertIn("previous", response.data)  # type: ignore

        if len(response.data["sessions"]) > 0:  # type: ignore
            session = response.data["sessions"][0]  # type: ignore
            self.assertIsInstance(session["session_id"], str)
            self.assertIsInstance(session["ip_address"], str)
            self.assertIsInstance(session["user_agent"], str)
            self.assertIsNotNone(session["last_activity_at"])

    def test_delete_session_response_format(self):
        """Test that DELETE response has correct format"""
        response = self.client.delete(
            self.url, data={"session_id": str(self.session1.session_id)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, None)  # Empty response # type: ignore

    # ========== PAGINATION TESTS ==========

    def test_pagination_default_page_size(self):
        """Test that pagination uses default page size of 50"""
        # Create 55 sessions to test pagination
        for i in range(55):
            Session.objects.create(
                user=self.user,
                session_id=uuid.uuid4(),
                ip_address=f"192.168.1.{i}",
                user_agent=f"Test Agent {i}",
                last_activity_at=timezone.now(),
            )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["sessions"]), 50)  # type: ignore
        self.assertIsNotNone(response.data["next"])  # type: ignore
        self.assertIsNone(response.data["previous"])  # type: ignore

    def test_pagination_custom_page_size(self):
        """Test that pagination respects custom page_size parameter"""
        # Create 30 sessions
        for i in range(30):
            Session.objects.create(
                user=self.user,
                session_id=uuid.uuid4(),
                ip_address=f"192.168.1.{i}",
                user_agent=f"Test Agent {i}",
                last_activity_at=timezone.now(),
            )

        response = self.client.get(self.url, {"page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["sessions"]), 10)  # type: ignore
        self.assertIsNotNone(response.data["next"])  # type: ignore
        self.assertIsNone(response.data["previous"])  # type: ignore

    def test_pagination_max_page_size(self):
        """Test that pagination respects max_page_size limit of 100"""
        # Create 150 sessions
        for i in range(150):
            Session.objects.create(
                user=self.user,
                session_id=uuid.uuid4(),
                ip_address=f"192.168.1.{i}",
                user_agent=f"Test Agent {i}",
                last_activity_at=timezone.now(),
            )

        response = self.client.get(self.url, {"page_size": 200})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return max_page_size (100) instead of requested 200
        self.assertEqual(len(response.data["sessions"]), 100)  # type: ignore

    def test_pagination_second_page(self):
        """Test that pagination works for second page"""
        # Create 55 sessions
        for i in range(55):
            Session.objects.create(
                user=self.user,
                session_id=uuid.uuid4(),
                ip_address=f"192.168.1.{i}",
                user_agent=f"Test Agent {i}",
                last_activity_at=timezone.now(),
            )

        response = self.client.get(self.url, {"page": 2, "page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["sessions"]), 10)  # type: ignore
        # Should have next and previous links
        self.assertIsNotNone(response.data["next"])  # type: ignore
        self.assertIsNotNone(response.data["previous"])  # type: ignore

    def test_pagination_invalid_page(self):
        """Test that pagination handles invalid page number gracefully"""
        # Create 10 sessions
        for i in range(10):
            Session.objects.create(
                user=self.user,
                session_id=uuid.uuid4(),
                ip_address=f"192.168.1.{i}",
                user_agent=f"Test Agent {i}",
                last_activity_at=timezone.now(),
            )

        response = self.client.get(self.url, {"page": 999})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pagination_with_sessions_less_than_page_size(self):
        """Test pagination when total sessions are less than page size"""
        # Create only 5 sessions
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["sessions"]), 2)  # type: ignore (from setUp)
        self.assertIsNone(response.data["next"])  # type: ignore
        self.assertIsNone(response.data["previous"])  # type: ignore

    def test_pagination_response_structure(self):
        """Test that pagination response has all required fields"""
        # Create 25 sessions
        for i in range(25):
            Session.objects.create(
                user=self.user,
                session_id=uuid.uuid4(),
                ip_address=f"192.168.1.{i}",
                user_agent=f"Test Agent {i}",
                last_activity_at=timezone.now(),
            )

        response = self.client.get(self.url, {"page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify response structure
        self.assertIn("next", response.data)  # type: ignore
        self.assertIn("previous", response.data)  # type: ignore
        self.assertIn("sessions", response.data)  # type: ignore

        # Verify sessions is a list
        self.assertIsInstance(response.data["sessions"], list)  # type: ignore
        self.assertEqual(len(response.data["sessions"]), 10)  # type: ignore

        # Verify each session has required fields
        for session in response.data["sessions"]:  # type: ignore
            self.assertIn("session_id", session)
            self.assertIn("ip_address", session)
            self.assertIn("user_agent", session)
            self.assertIn("last_activity_at", session)
