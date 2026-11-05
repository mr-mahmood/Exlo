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

        updated = serializer.save()
        self.assertEqual(updated.status, GymAnnouncement.Status.PUBLISHED)
        self.assertIsNotNone(updated.published_at)
        updated.refresh_from_db()
        self.assertEqual(updated.status, GymAnnouncement.Status.PUBLISHED)
        self.assertIsNotNone(updated.published_at)

    def make_announcement(self):
        return GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.user,
            title="Original title",
            content="Original content",
        )

    def test_stale_serializer_cannot_republish_archived_announcement(self):
        announcement = self.make_announcement()
        serializer = GymAnnouncementSerializer(
            announcement,
            data={"status": "PUBLISHED", "title": "Rejected"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        current = GymAnnouncement.objects.get(pk=announcement.pk)
        current.archive()
        original = GymAnnouncement.objects.values().get(pk=announcement.pk)

        with self.assertRaises(APIError) as raised:
            serializer.save()

        self.assertEqual(raised.exception.error_code, "ANNOU_003")
        self.assertEqual(
            GymAnnouncement.objects.values().get(pk=announcement.pk), original
        )

    def test_deleted_announcement_is_not_recreated_by_stale_update(self):
        announcement = self.make_announcement()
        serializer = GymAnnouncementSerializer(
            announcement, data={"status": "PUBLISHED"}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        GymAnnouncement.objects.filter(pk=announcement.pk).delete()

        with self.assertRaises(APIError) as raised:
            serializer.save()

        self.assertEqual(raised.exception.error_code, "ANNOU_001")
        self.assertFalse(GymAnnouncement.objects.filter(pk=announcement.pk).exists())

    def test_stale_content_edit_preserves_latest_publication_state(self):
        for state in ("PUBLISHED", "ARCHIVED"):
            with self.subTest(state=state):
                announcement = self.make_announcement()
                serializer = GymAnnouncementSerializer(
                    announcement, data={"title": "Edited title"}, partial=True
                )
                self.assertTrue(serializer.is_valid(), serializer.errors)
                current = GymAnnouncement.objects.get(pk=announcement.pk)
                if state == "PUBLISHED":
                    current.publish()
                else:
                    current.archive()
                timestamps = (current.published_at, current.archived_at)

                serializer.save()

                announcement.refresh_from_db()
                self.assertEqual(announcement.title, "Edited title")
                self.assertEqual(announcement.status, state)
                self.assertEqual(
                    (announcement.published_at, announcement.archived_at), timestamps
                )
