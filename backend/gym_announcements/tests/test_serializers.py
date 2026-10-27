# gym_announcements/tests/test_serializers.py


import uuid
from django.test import TestCase
from gym.models import Gym
from core.errors import APIError, GymAnnouncementError
from users.models import User
from gym_announcements.serializers import GymAnnouncementSerializer
from gym_announcements.models import GymAnnouncement
from django.conf import settings


class GymAnnouncementSerializerTest(TestCase):
    """Test cases for GymAnnouncementSerializer."""

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="09121234567",
            first_name="Test",
            last_name="User",
        )
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
        )
        self.announcement_data = {
            "title": "Test Announcement",
            "content": "This is a test announcement content.",
        }

    def test_serializer_valid_data(self):
        """Test serializer with valid data."""
        serializer = GymAnnouncementSerializer(
            data=self.announcement_data, context={"gym": self.gym}
        )
        self.assertTrue(serializer.is_valid())

        announcement = serializer.save(author=self.user)
        self.assertEqual(announcement.title, "Test Announcement")
        self.assertEqual(announcement.content, "This is a test announcement content.")
        self.assertEqual(announcement.gym, self.gym)
        self.assertEqual(announcement.author, self.user)
        self.assertEqual(announcement.status, GymAnnouncement.Status.DRAFT)

    def test_serializer_missing_gym_context(self):
        """Test serializer without gym in context."""
        serializer = GymAnnouncementSerializer(data=self.announcement_data)
        self.assertTrue(serializer.is_valid())

        with self.assertRaises(APIError) as context:
            serializer.save(author=self.user)
        self.assertEqual(
            context.exception.error_code,
            GymAnnouncementError.GYM_REQUIRED[0],
        )

    def test_serializer_read_only_fields(self):
        """Test that read-only fields are not writable."""
        data = {
            **self.announcement_data,
            "id": str(uuid.uuid7()),
            "published_at": "2024-01-01T00:00:00Z",
            "archived_at": "2024-01-02T00:00:00Z",
        }
        serializer = GymAnnouncementSerializer(data=data, context={"gym": self.gym})
        self.assertTrue(serializer.is_valid())

        announcement = serializer.save(author=self.user)
        self.assertNotEqual(str(announcement.id), data["id"])
        self.assertIsNone(announcement.published_at)
        self.assertIsNone(announcement.archived_at)

    def test_serializer_author_field(self):
        """Test that author field is read-only and shows correct data."""
        announcement = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.user,
            title="Test Announcement",
            content="Test Content",
            status=GymAnnouncement.Status.DRAFT,
        )

        serializer = GymAnnouncementSerializer(announcement)
        self.assertIn("author", serializer.data)
        self.assertEqual(serializer.data["author"]["first_name"], "Test")
        self.assertEqual(serializer.data["author"]["last_name"], "User")
        self.assertEqual(serializer.data["author"]["phone_number"], "09121234567")

    def test_serializer_create_sets_default_status(self):
        """Test that new announcements are created with DRAFT status."""
        serializer = GymAnnouncementSerializer(
            data=self.announcement_data, context={"gym": self.gym}
        )
        self.assertTrue(serializer.is_valid())

        announcement = serializer.save(author=self.user)
        self.assertEqual(announcement.status, GymAnnouncement.Status.DRAFT)

    def test_serializer_update(self):
        """Test updating an announcement."""
        announcement = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.user,
            title="Original Title",
            content="Original Content",
            status=GymAnnouncement.Status.DRAFT,
        )

        update_data = {
            "title": "Updated Title",
            "content": "Updated Content",
        }
        serializer = GymAnnouncementSerializer(
            instance=announcement,
            data=update_data,
            partial=True,
            context={"gym": self.gym},
        )
        self.assertTrue(serializer.is_valid())

        updated = serializer.save()
        self.assertEqual(updated.title, "Updated Title")
        self.assertEqual(updated.content, "Updated Content")
        self.assertEqual(updated.status, GymAnnouncement.Status.DRAFT)

    def test_serializer_update_status_allowed(self):
        """Test that status can be updated through serializer."""
        announcement = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.user,
            title="Test Title",
            content="Test Content",
            status=GymAnnouncement.Status.DRAFT,
        )

        update_data = {
            "status": GymAnnouncement.Status.PUBLISHED,
        }
        serializer = GymAnnouncementSerializer(
            instance=announcement,
            data=update_data,
            partial=True,
            context={"gym": self.gym},
        )
        self.assertTrue(serializer.is_valid())

        # Status should remain DRAFT because it's read-only
        updated = serializer.save()
        self.assertEqual(updated.status, GymAnnouncement.Status.PUBLISHED)
