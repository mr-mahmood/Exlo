# user_sessions/tests/test_models.py


from django.test import TestCase, RequestFactory
from django.utils import timezone
from users.models import User
from users_sessions.models import Session
from django.conf import settings


class SessionModelTest(TestCase):
    """Test Session model"""

    def setUp(self):
        settings.DEBUG = True
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )
        self.factory = RequestFactory()

    def test_create_session(self):
        """Test creating a session"""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session = Session.create_session(self.user, request)

        self.assertEqual(session.user, self.user)
        self.assertEqual(session.ip_address, "127.0.0.1")
        self.assertEqual(session.user_agent, "Test Agent")
        self.assertIsNotNone(session.session_id)
        self.assertIsNotNone(session.last_activity_at)

    def test_create_session_with_x_forwarded_for(self):
        """Test session creation with X-Forwarded-For header"""
        request = self.factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "192.168.1.1, 10.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session = Session.create_session(self.user, request)

        # Should take first IP
        self.assertEqual(session.ip_address, "192.168.1.1")

    def test_create_session_without_ip(self):
        """Test session creation without IP address"""
        request = self.factory.get("/")
        request.META.pop("REMOTE_ADDR", None)
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session = Session.create_session(self.user, request)

        self.assertEqual(session.ip_address, "0.0.0.0")

    def test_create_session_without_user_agent(self):
        """Test session creation without user agent"""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META.pop("HTTP_USER_AGENT", None)

        session = Session.create_session(self.user, request)

        self.assertEqual(session.user_agent, "Unknown Client")

    def test_update_last_activity_at(self):
        """Test updating last activity timestamp"""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session = Session.create_session(self.user, request)
        old_time = session.last_activity_at

        # Wait a moment
        import time

        time.sleep(0.1)

        session.update_last_activity_at()
        session.refresh_from_db()

        self.assertNotEqual(session.last_activity_at, old_time)

    def test_session_str(self):
        """Test string representation"""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session = Session.create_session(self.user, request)
        self.assertEqual(str(session), "127.0.0.1")

    def test_session_unique_session_id(self):
        """Test session_id is unique"""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session1 = Session.create_session(self.user, request)
        session2 = Session.create_session(self.user, request)

        self.assertNotEqual(session1.session_id, session2.session_id)

    def test_create_session_ip_truncation(self):
        """Test that IP addresses longer than 45 chars are truncated"""
        request = self.factory.get("/")
        long_ip = "123.456.789.012.345.678.901.234.567.890.123.456.789.012.345.678.901.234.567.890.123.456.789"
        request.META["HTTP_X_FORWARDED_FOR"] = long_ip
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session = Session.create_session(self.user, request)

        # Should be truncated to 45 characters
        self.assertEqual(len(session.ip_address), 45)
        self.assertEqual(session.ip_address, long_ip[:45])

    def test_create_session_user_agent_truncation(self):
        """Test that user agents longer than 255 chars are truncated"""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        long_user_agent = "A" * 300  # 300 characters
        request.META["HTTP_USER_AGENT"] = long_user_agent

        session = Session.create_session(self.user, request)

        # Should be truncated to 255 characters
        self.assertEqual(len(session.user_agent), 255)
        self.assertEqual(session.user_agent, long_user_agent[:255])

    def test_create_session_with_empty_user_agent_string(self):
        """Test session creation with empty user agent string"""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = ""  # Empty string

        session = Session.create_session(self.user, request)

        # Should use default "Unknown Client"
        self.assertEqual(session.user_agent, "Unknown Client")

    def test_create_session_ip_with_spaces(self):
        """Test that IP addresses with spaces are handled correctly"""
        request = self.factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = " 192.168.1.1 , 10.0.0.1 "
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session = Session.create_session(self.user, request)

        # Should strip spaces and take first IP
        self.assertEqual(session.ip_address, "192.168.1.1")

    def test_create_session_meta_keys_not_present(self):
        """Test session creation when META keys are not present"""
        request = self.factory.get("/")
        # Remove the default REMOTE_ADDR that RequestFactory adds
        if "REMOTE_ADDR" in request.META:
            del request.META["REMOTE_ADDR"]
        # Remove HTTP_USER_AGENT if it exists
        if "HTTP_USER_AGENT" in request.META:
            del request.META["HTTP_USER_AGENT"]

        session = Session.create_session(self.user, request)

        # Should use defaults
        self.assertEqual(session.ip_address, "0.0.0.0")
        self.assertEqual(session.user_agent, "Unknown Client")
        self.assertIsNotNone(session.session_id)

    def test_session_relationship_with_user(self):
        """Test the relationship between Session and User"""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session = Session.create_session(self.user, request)

        # Test user can access sessions
        self.assertEqual(self.user.sessions.count(), 1)
        self.assertEqual(self.user.sessions.first(), session)

        # Test deleting user deletes sessions
        self.user.delete()
        self.assertEqual(Session.objects.count(), 0)

    def test_session_ordering(self):
        """Test that sessions are ordered by created_at desc"""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session1 = Session.create_session(self.user, request)

        # Wait a moment to ensure different timestamps
        import time

        time.sleep(0.1)

        session2 = Session.create_session(self.user, request)

        # Query should return most recent first
        sessions = Session.objects.all()
        self.assertEqual(sessions[0], session2)
        self.assertEqual(sessions[1], session1)

    def test_update_last_activity_at_triggers_updated_at(self):
        """Test that updating last_activity_at also updates updated_at"""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        session = Session.create_session(self.user, request)
        old_updated_at = session.updated_at

        # Wait a moment
        import time

        time.sleep(0.1)

        session.update_last_activity_at()
        session.refresh_from_db()

        self.assertNotEqual(session.updated_at, old_updated_at)
