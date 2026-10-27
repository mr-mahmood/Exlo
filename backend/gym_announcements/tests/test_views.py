# gym_announcements/tests/test_views.py


import uuid
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from users.models import User
from gym.models import Gym
from gym_announcements.models import GymAnnouncement
from gym_auth.models import UserGymRole
from django.conf import settings


class GymAnnouncementViewsTest(TestCase):
    """Test cases for GymAnnouncement views."""

    def setUp(self):
        self.client = APIClient()

        # Create users
        self.admin_user = User.objects.create_superuser(
            phone_number="09121234567",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
        )

        self.gym_owner = User.objects.create_user(
            phone_number="09129876543",
            first_name="Owner",
            last_name="User",
        )

        self.gym_member = User.objects.create_user(
            phone_number="09121112222",
            first_name="Member",
            last_name="User",
        )

        self.regular_user = User.objects.create_user(
            phone_number="09123334444",
            first_name="Regular",
            last_name="User",
        )

        # Create gym
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
        )

        UserGymRole.objects.create(
            user=self.gym_owner, gym=self.gym, role=UserGymRole.Role.OWNER
        )

        # Create test announcements
        self.announcement1 = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.gym_owner,
            title="Published Announcement",
            content="This is a published announcement.",
            status=GymAnnouncement.Status.PUBLISHED,
            published_at=timezone.now(),
        )

        self.announcement2 = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.gym_owner,
            title="Draft Announcement",
            content="This is a draft announcement.",
            status=GymAnnouncement.Status.DRAFT,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    # ==================== LIST TESTS ====================

    def test_announcement_list_gym_member_access(self):
        """Test that gym members can view published announcements."""
        self.authenticate(self.gym_member)

        response = self.client.get(
            reverse("gym_announcements:list", kwargs={"gym_id": self.gym.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["announcements"]), 1)
        self.assertEqual(
            response.data["announcements"][0]["title"], "Published Announcement"
        )

    def test_announcement_list_unauthenticated_no_access(self):
        """Test that unauthenticated users cannot view announcements."""
        response = self.client.get(
            reverse("gym_announcements:list", kwargs={"gym_id": self.gym.id})
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_announcement_list_gym_not_found(self):
        """Test announcement list with non-existent gym."""
        self.authenticate(self.gym_member)
        non_existent_id = uuid.uuid7()

        response = self.client.get(
            reverse("gym_announcements:list", kwargs={"gym_id": non_existent_id})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_announcement_list_pagination(self):
        """Test that announcement list is paginated."""
        for i in range(65):
            GymAnnouncement.objects.create(
                gym=self.gym,
                author=self.gym_owner,
                title=f"Announcement {i}",
                content=f"Content {i}",
                status=GymAnnouncement.Status.PUBLISHED,
                published_at=timezone.now(),
            )

        self.authenticate(self.gym_member)
        response = self.client.get(
            reverse("gym_announcements:list", kwargs={"gym_id": self.gym.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["announcements"]), 50)

    # ==================== CREATE TESTS ====================

    def test_announcement_create_gym_owner(self):
        """Test that gym owner can create an announcement."""
        self.authenticate(self.gym_owner)

        data = {
            "title": "New Announcement",
            "content": "This is a new announcement.",
        }

        response = self.client.post(
            reverse("gym_announcements:create", kwargs={"gym_id": self.gym.id}), data
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["announcement"]["title"], "New Announcement")
        self.assertEqual(
            response.data["announcement"]["status"], GymAnnouncement.Status.DRAFT
        )

    def test_announcement_create_gym_member_denied(self):
        """Test that gym member cannot create announcements."""
        self.authenticate(self.gym_member)

        data = {
            "title": "Member Announcement",
            "content": "This is a member announcement.",
        }

        response = self.client.post(
            reverse("gym_announcements:create", kwargs={"gym_id": self.gym.id}), data
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_announcement_create_missing_title(self):
        """Test creating announcement without title."""
        self.authenticate(self.gym_owner)

        data = {"content": "This is a new announcement."}

        response = self.client.post(
            reverse("gym_announcements:create", kwargs={"gym_id": self.gym.id}), data
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==================== UPDATE TESTS ====================

    def test_announcement_update_gym_owner(self):
        """Test that gym owner can update their announcement."""
        self.authenticate(self.gym_owner)

        data = {
            "title": "Updated Title",
            "content": "Updated content.",
        }

        response = self.client.put(
            reverse(
                "gym_announcements:update",
                kwargs={
                    "gym_id": self.gym.id,
                    "announcement_id": self.announcement1.id,
                },
            ),
            data,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["announcement"]["title"], "Updated Title")

    def test_announcement_update_gym_member_denied(self):
        """Test that gym member cannot update announcements."""
        self.authenticate(self.gym_member)

        data = {"title": "Hacked Title"}

        response = self.client.put(
            reverse(
                "gym_announcements:update",
                kwargs={
                    "gym_id": self.gym.id,
                    "announcement_id": self.announcement1.id,
                },
            ),
            data,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_announcement_update_not_found(self):
        """Test updating non-existent announcement."""
        self.authenticate(self.gym_owner)
        non_existent_id = uuid.uuid7()

        data = {"title": "New Title"}

        response = self.client.put(
            reverse(
                "gym_announcements:update",
                kwargs={"gym_id": self.gym.id, "announcement_id": non_existent_id},
            ),
            data,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_announcement_update_other_gym_announcement(self):
        """Test that gym owner cannot update announcement from other gym."""
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
        )
        other_announcement = GymAnnouncement.objects.create(
            gym=other_gym,
            author=self.gym_owner,
            title="Other Gym Announcement",
            content="This belongs to other gym.",
            status=GymAnnouncement.Status.DRAFT,
        )

        self.authenticate(self.gym_owner)

        data = {"title": "Hacked Title"}

        response = self.client.put(
            reverse(
                "gym_announcements:update",
                kwargs={
                    "gym_id": other_gym.id,
                    "announcement_id": other_announcement.id,
                },
            ),
            data,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== DELETE TESTS ====================

    def test_announcement_delete_gym_owner(self):
        """Test that gym owner can delete their announcement."""
        self.authenticate(self.gym_owner)

        response = self.client.delete(
            reverse(
                "gym_announcements:delete",
                kwargs={
                    "gym_id": self.gym.id,
                    "announcement_id": self.announcement1.id,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        with self.assertRaises(GymAnnouncement.DoesNotExist):
            GymAnnouncement.objects.get(id=self.announcement1.id)

    def test_announcement_delete_gym_member_denied(self):
        """Test that gym member cannot delete announcements."""
        self.authenticate(self.gym_member)

        response = self.client.delete(
            reverse(
                "gym_announcements:delete",
                kwargs={
                    "gym_id": self.gym.id,
                    "announcement_id": self.announcement1.id,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_announcement_delete_not_found(self):
        """Test deleting non-existent announcement."""
        self.authenticate(self.gym_owner)
        non_existent_id = uuid.uuid7()

        response = self.client.delete(
            reverse(
                "gym_announcements:delete",
                kwargs={"gym_id": self.gym.id, "announcement_id": non_existent_id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_announcement_delete_other_gym_announcement(self):
        """Test that gym owner cannot delete announcement from other gym."""
        other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="Other Address",
        )
        other_announcement = GymAnnouncement.objects.create(
            gym=other_gym,
            author=self.gym_owner,
            title="Other Gym Announcement",
            content="This belongs to other gym.",
            status=GymAnnouncement.Status.DRAFT,
        )

        self.authenticate(self.gym_owner)

        response = self.client.delete(
            reverse(
                "gym_announcements:delete",
                kwargs={
                    "gym_id": other_gym.id,
                    "announcement_id": other_announcement.id,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== MODEL METHOD TESTS ====================

    def test_announcement_publish_method(self):
        """Test the publish method on announcement model."""
        draft = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.gym_owner,
            title="Draft Announcement",
            content="This is a draft.",
            status=GymAnnouncement.Status.DRAFT,
        )

        self.assertTrue(draft.is_draft)
        self.assertIsNone(draft.published_at)

        draft.publish()

        self.assertTrue(draft.is_published)
        self.assertIsNotNone(draft.published_at)

    def test_announcement_archive_method(self):
        """Test the archive method on announcement model."""
        published = GymAnnouncement.objects.create(
            gym=self.gym,
            author=self.gym_owner,
            title="Published Announcement",
            content="This is published.",
            status=GymAnnouncement.Status.PUBLISHED,
            published_at=timezone.now(),
        )

        self.assertFalse(published.is_archived)

        published.archive()

        self.assertTrue(published.is_archived)
        self.assertIsNotNone(published.archived_at)
