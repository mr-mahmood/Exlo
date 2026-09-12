# gym_announcements/tests/test_models.py
# type: ignore

import uuid
from django.test import TestCase
from django.utils import timezone
from gym.models import Gym
from gym_announcements.models import GymAnnouncement
from users.models import User
from django.conf import settings


class GymAnnouncementModelTest(TestCase):
    """Test cases for GymAnnouncement model."""

    def setUp(self):
        settings.DEBUG = True

        # Create a user (author)
        self.author = User.objects.create_user(
            phone_number="09121234567",
            first_name="Test",
            last_name="Author",
        )

        # Create a gym
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
        )

        # Create a gym announcement
        self.announcement_data = {
            "gym": self.gym,
            "author": self.author,
            "title": "Test Announcement",
            "content": "This is a test announcement content.",
            "status": GymAnnouncement.Status.DRAFT,
        }

    def test_create_announcement_success(self):
        """Test creating a gym announcement successfully."""
        announcement = GymAnnouncement.objects.create(**self.announcement_data)

        self.assertEqual(announcement.gym, self.gym)
        self.assertEqual(announcement.author, self.author)
        self.assertEqual(announcement.title, "Test Announcement")
        self.assertEqual(announcement.content, "This is a test announcement content.")
        self.assertEqual(announcement.status, GymAnnouncement.Status.DRAFT)
        self.assertIsNotNone(announcement.id)
        self.assertIsInstance(announcement.id, uuid.UUID)
        self.assertIsNone(announcement.published_at)
        self.assertIsNone(announcement.archived_at)
        self.assertIsNotNone(announcement.created_at)
        self.assertIsNotNone(announcement.updated_at)

    def test_announcement_default_status(self):
        """Test that announcement default status is DRAFT."""
        announcement = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Default Status Test",
            content="Testing default status.",
        )

        self.assertEqual(announcement.status, GymAnnouncement.Status.DRAFT)

    def test_announcement_related_name(self):
        """Test accessing announcements through gym's related_name."""
        announcement1 = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Announcement 1",
            content="Content 1",
            status=GymAnnouncement.Status.DRAFT,
        )
        announcement2 = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Announcement 2",
            content="Content 2",
            status=GymAnnouncement.Status.DRAFT,
        )

        announcements = self.gym.announcements.all()
        self.assertEqual(announcements.count(), 2)
        self.assertIn(announcement1, announcements)
        self.assertIn(announcement2, announcements)

    def test_announcement_author_related_name(self):
        """Test accessing announcements through author's related_name."""
        announcement1 = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Announcement 1",
            content="Content 1",
            status=GymAnnouncement.Status.DRAFT,
        )
        announcement2 = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Announcement 2",
            content="Content 2",
            status=GymAnnouncement.Status.DRAFT,
        )

        announcements = self.author.gym_announcements.all()
        self.assertEqual(announcements.count(), 2)
        self.assertIn(announcement1, announcements)
        self.assertIn(announcement2, announcements)

    def test_announcement_cascade_delete_gym(self):
        """Test that announcements are deleted when gym is deleted."""
        announcement = GymAnnouncement.objects.create(**self.announcement_data)
        announcement_id = announcement.id
        gym_id = self.gym.id

        self.gym.delete()

        with self.assertRaises(GymAnnouncement.DoesNotExist):
            GymAnnouncement.objects.get(id=announcement_id)

        # Gym should be deleted
        with self.assertRaises(Gym.DoesNotExist):
            Gym.objects.get(id=gym_id)

    def test_announcement_cascade_delete_author(self):
        """Test that announcements are deleted when author is deleted."""
        announcement = GymAnnouncement.objects.create(**self.announcement_data)
        announcement_id = announcement.id
        author_id = self.author.id

        self.author.delete()

        with self.assertRaises(GymAnnouncement.DoesNotExist):
            GymAnnouncement.objects.get(id=announcement_id)

        # Author should be deleted
        with self.assertRaises(User.DoesNotExist):
            User.objects.get(id=author_id)

    def test_announcement_str_method(self):
        """Test the __str__ method of GymAnnouncement."""
        announcement = GymAnnouncement.objects.create(**self.announcement_data)
        expected = f"announcement: {announcement.title}, Gym: {announcement.gym.name}, User: {announcement.author.full_name}"
        self.assertEqual(str(announcement), expected)

    def test_announcement_ordering(self):
        """Test that announcements are ordered by created_at descending."""
        announcement1 = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="First Announcement",
            content="Content 1",
            status=GymAnnouncement.Status.DRAFT,
        )

        # Create second announcement with a slight delay
        import time

        time.sleep(0.1)  # Small delay to ensure different timestamps

        announcement2 = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Second Announcement",
            content="Content 2",
            status=GymAnnouncement.Status.DRAFT,
        )

        announcements = GymAnnouncement.objects.all()
        self.assertEqual(announcements[0], announcement2)  # Most recent first
        self.assertEqual(announcements[1], announcement1)

    # ==================== STATUS PROPERTY TESTS ====================

    def test_is_draft_property(self):
        """Test the is_draft property."""
        draft = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Draft Announcement",
            content="Draft content.",
            status=GymAnnouncement.Status.DRAFT,
        )
        published = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Published Announcement",
            content="Published content.",
            status=GymAnnouncement.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        archived = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Archived Announcement",
            content="Archived content.",
            status=GymAnnouncement.Status.ARCHIVED,
            archived_at=timezone.now(),
        )

        self.assertTrue(draft.is_draft)
        self.assertFalse(published.is_draft)
        self.assertFalse(archived.is_draft)

    def test_is_published_property(self):
        """Test the is_published property."""
        draft = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Draft Announcement",
            content="Draft content.",
            status=GymAnnouncement.Status.DRAFT,
        )
        published = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Published Announcement",
            content="Published content.",
            status=GymAnnouncement.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        archived = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Archived Announcement",
            content="Archived content.",
            status=GymAnnouncement.Status.ARCHIVED,
            archived_at=timezone.now(),
        )

        self.assertFalse(draft.is_published)
        self.assertTrue(published.is_published)
        self.assertFalse(archived.is_published)

    def test_is_archived_property(self):
        """Test the is_archived property."""
        draft = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Draft Announcement",
            content="Draft content.",
            status=GymAnnouncement.Status.DRAFT,
        )
        published = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Published Announcement",
            content="Published content.",
            status=GymAnnouncement.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        archived = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Archived Announcement",
            content="Archived content.",
            status=GymAnnouncement.Status.ARCHIVED,
            archived_at=timezone.now(),
        )

        self.assertFalse(draft.is_archived)
        self.assertFalse(published.is_archived)
        self.assertTrue(archived.is_archived)

    # ==================== STATUS METHOD TESTS ====================

    def test_publish_method_from_draft(self):
        """Test publishing a draft announcement."""
        announcement = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Draft Announcement",
            content="This is a draft.",
            status=GymAnnouncement.Status.DRAFT,
        )

        self.assertTrue(announcement.is_draft)
        self.assertFalse(announcement.is_published)
        self.assertIsNone(announcement.published_at)

        announcement.publish()
        announcement.refresh_from_db()

        self.assertFalse(announcement.is_draft)
        self.assertTrue(announcement.is_published)
        self.assertIsNotNone(announcement.published_at)

    def test_publish_method_already_published(self):
        """Test publishing an already published announcement."""
        announcement = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Published Announcement",
            content="This is published.",
            status=GymAnnouncement.Status.PUBLISHED,
            published_at=timezone.now(),
        )

        original_published_at = announcement.published_at

        announcement.publish()
        announcement.refresh_from_db()

        self.assertTrue(announcement.is_published)
        self.assertEqual(announcement.published_at, original_published_at)

    def test_publish_method_from_archived(self):
        """Test publishing an archived announcement (should not work)."""
        announcement = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Archived Announcement",
            content="This is archived.",
            status=GymAnnouncement.Status.ARCHIVED,
            archived_at=timezone.now(),
        )

        announcement.publish()
        announcement.refresh_from_db()

        self.assertFalse(announcement.is_published)
        self.assertTrue(announcement.is_archived)

    def test_archive_method_from_draft(self):
        """Test archiving a draft announcement."""
        announcement = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Draft Announcement",
            content="This is a draft.",
            status=GymAnnouncement.Status.DRAFT,
        )

        self.assertFalse(announcement.is_archived)
        self.assertIsNone(announcement.archived_at)

        announcement.archive()
        announcement.refresh_from_db()

        self.assertTrue(announcement.is_archived)
        self.assertIsNotNone(announcement.archived_at)

    def test_archive_method_from_published(self):
        """Test archiving a published announcement."""
        announcement = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Published Announcement",
            content="This is published.",
            status=GymAnnouncement.Status.PUBLISHED,
            published_at=timezone.now(),
        )

        self.assertFalse(announcement.is_archived)
        self.assertIsNone(announcement.archived_at)

        announcement.archive()
        announcement.refresh_from_db()

        self.assertTrue(announcement.is_archived)
        self.assertIsNotNone(announcement.archived_at)

    def test_archive_method_already_archived(self):
        """Test archiving an already archived announcement."""
        announcement = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.author,
            title="Archived Announcement",
            content="This is archived.",
            status=GymAnnouncement.Status.ARCHIVED,
            archived_at=timezone.now(),
        )

        original_archived_at = announcement.archived_at

        announcement.archive()
        announcement.refresh_from_db()

        self.assertTrue(announcement.is_archived)
        self.assertEqual(announcement.archived_at, original_archived_at)
