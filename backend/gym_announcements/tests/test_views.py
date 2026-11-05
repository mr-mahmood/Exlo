# gym_announcements/tests/test_views.py


import uuid
from datetime import timedelta
from django.core.cache import cache
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from core.cache import GYM_ANNOUNCEMENTS, cache_key
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


class GymAnnouncementPublicationViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(phone_number="09120000001")
        cls.other_owner = User.objects.create_user(phone_number="09120000002")
        cls.admin = User.objects.create_superuser(
            phone_number="09120000003", password="adminpass123"
        )
        cls.gym = Gym.objects.create(
            name="Test Gym", province="Tehran", city="Tehran", address="Address"
        )
        cls.other_gym = Gym.objects.create(
            name="Other Gym", province="Tehran", city="Tehran", address="Address"
        )
        for gym, owner in ((cls.gym, cls.owner), (cls.other_gym, cls.other_owner)):
            UserGymRole.objects.create(
                gym=gym, user=owner, role=UserGymRole.Role.OWNER
            )

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def make_announcement(self, state="DRAFT", gym=None):
        earlier = timezone.now() - timedelta(days=2)
        return GymAnnouncement.objects.create(
            gym=gym or self.gym,
            author=self.owner,
            title="Original title",
            content="Original content",
            status=state,
            published_at=earlier if state != "DRAFT" else None,
            archived_at=earlier if state == "ARCHIVED" else None,
        )

    def update(self, announcement, data, gym=None):
        return self.client.put(
            reverse(
                "gym_announcements:update",
                kwargs={
                    "gym_id": (gym or self.gym).pk,
                    "announcement_id": announcement.pk,
                },
            ),
            data,
            format="json",
        )

    def list_announcements(self, gym=None):
        response = self.client.get(
            reverse("gym_announcements:list", kwargs={"gym_id": (gym or self.gym).pk})
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]["announcements"]

    @timezone.override("UTC")
    def test_allowed_transitions_set_server_timestamps(self):
        for initial, target in (
            ("DRAFT", "PUBLISHED"),
            ("DRAFT", "ARCHIVED"),
            ("PUBLISHED", "ARCHIVED"),
        ):
            with self.subTest(initial=initial, target=target):
                announcement = self.make_announcement(initial)
                original_published_at = announcement.published_at
                before = timezone.now()
                response = self.update(
                    announcement,
                    {
                        "status": target,
                        "title": "Updated title",
                        "content": "Updated content",
                        "published_at": "2000-01-01T00:00:00Z",
                        "archived_at": "2000-01-01T00:00:00Z",
                    },
                )
                after = timezone.now()

                self.assertEqual(response.status_code, 200)
                announcement.refresh_from_db()
                self.assertEqual(announcement.status, target)
                self.assertEqual(announcement.title, "Updated title")
                self.assertEqual(announcement.content, "Updated content")
                timestamp = (
                    announcement.published_at
                    if target == "PUBLISHED"
                    else announcement.archived_at
                )
                self.assertIsNotNone(timestamp)
                self.assertLessEqual(before, timestamp)
                self.assertLessEqual(timestamp, after)
                if target == "ARCHIVED":
                    self.assertEqual(announcement.published_at, original_published_at)
                else:
                    self.assertIsNone(announcement.archived_at)
                payload = response.json()
                self.assertTrue(payload["success"])
                self.assertIsNone(payload["error_code"])
                for field in ("published_at", "archived_at"):
                    value = payload["data"]["announcement"][field]
                    self.assertEqual(
                        parse_datetime(value) if value else None,
                        getattr(announcement, field),
                    )

    def test_forbidden_transitions_preserve_all_fields_and_cache(self):
        self.client.force_authenticate(user=self.admin)
        for initial, target in (
            ("PUBLISHED", "DRAFT"),
            ("ARCHIVED", "DRAFT"),
            ("ARCHIVED", "PUBLISHED"),
        ):
            with self.subTest(initial=initial, target=target):
                announcement = self.make_announcement(initial)
                original = GymAnnouncement.objects.values().get(pk=announcement.pk)
                self.list_announcements()
                key = cache_key(GYM_ANNOUNCEMENTS, self.gym.pk)
                warmed = cache.get(key)
                with self.captureOnCommitCallbacks(execute=True) as callbacks:
                    response = self.update(
                        announcement,
                        {"status": target, "title": "Rejected", "content": "Rejected"},
                    )

                self.assertEqual(response.status_code, 400)
                payload = response.json()
                self.assertFalse(payload["success"])
                self.assertIsNone(payload["data"])
                self.assertEqual(payload["error_code"], "ANNOU_003")
                self.assertEqual(
                    GymAnnouncement.objects.values().get(pk=announcement.pk), original
                )
                self.assertEqual(callbacks, [])
                self.assertEqual(cache_key(GYM_ANNOUNCEMENTS, self.gym.pk), key)
                self.assertEqual(cache.get(key), warmed)

    def test_repeated_status_requests_preserve_timestamps(self):
        for state in ("DRAFT", "PUBLISHED", "ARCHIVED"):
            with self.subTest(state=state):
                announcement = self.make_announcement(state)
                timestamps = (announcement.published_at, announcement.archived_at)
                for _ in range(2):
                    response = self.update(
                        announcement, {"status": state, "title": "Edited title"}
                    )
                    self.assertEqual(response.status_code, 200)
                    announcement.refresh_from_db()
                    self.assertEqual(announcement.status, state)
                    self.assertEqual(announcement.title, "Edited title")
                    self.assertEqual(
                        (announcement.published_at, announcement.archived_at),
                        timestamps,
                    )

    def test_content_only_update_preserves_publication_state(self):
        for state in ("DRAFT", "PUBLISHED", "ARCHIVED"):
            with self.subTest(state=state):
                announcement = self.make_announcement(state)
                timestamps = (announcement.published_at, announcement.archived_at)
                response = self.update(announcement, {"content": "Edited content"})
                self.assertEqual(response.status_code, 200)
                announcement.refresh_from_db()
                self.assertEqual(announcement.content, "Edited content")
                self.assertEqual(announcement.status, state)
                self.assertEqual(
                    (announcement.published_at, announcement.archived_at), timestamps
                )

    def test_create_with_explicit_status_sets_server_timestamps(self):
        for state in ("DRAFT", "PUBLISHED", "ARCHIVED"):
            with self.subTest(state=state):
                before = timezone.now()
                response = self.client.post(
                    reverse("gym_announcements:create", kwargs={"gym_id": self.gym.pk}),
                    {
                        "title": "Created title",
                        "content": "Created content",
                        "status": state,
                        "published_at": "2000-01-01T00:00:00Z",
                        "archived_at": "2000-01-01T00:00:00Z",
                    },
                    format="json",
                )
                after = timezone.now()
                self.assertEqual(response.status_code, 201)
                announcement = GymAnnouncement.objects.get(
                    pk=response.json()["data"]["announcement"]["id"]
                )
                self.assertEqual(announcement.status, state)
                self.assertEqual(announcement.gym_id, self.gym.pk)
                self.assertEqual(announcement.author_id, self.owner.pk)
                for field, populated in (
                    ("published_at", state == "PUBLISHED"),
                    ("archived_at", state == "ARCHIVED"),
                ):
                    timestamp = getattr(announcement, field)
                    if populated:
                        self.assertIsNotNone(timestamp)
                        self.assertLessEqual(before, timestamp)
                        self.assertLessEqual(timestamp, after)
                    else:
                        self.assertIsNone(timestamp)

    def test_invalid_status_does_not_change_announcement(self):
        announcement = self.make_announcement()
        original = GymAnnouncement.objects.values().get(pk=announcement.pk)
        for value in ("INVALID", "", None):
            with self.subTest(value=value):
                response = self.update(announcement, {"status": value, "title": "Bad"})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["success"])
                self.assertEqual(
                    GymAnnouncement.objects.values().get(pk=announcement.pk), original
                )

    def test_publish_and_archive_refresh_list_after_commit(self):
        announcement = self.make_announcement()
        self.assertEqual(self.list_announcements(), [])
        other_key = cache_key(GYM_ANNOUNCEMENTS, self.other_gym.pk)
        self.assertEqual(self.list_announcements(self.other_gym), [])

        for target, visible in (("PUBLISHED", True), ("ARCHIVED", False)):
            key = cache_key(GYM_ANNOUNCEMENTS, self.gym.pk)
            warmed = cache.get(key)
            with self.captureOnCommitCallbacks(execute=True):
                response = self.update(announcement, {"status": target})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(cache_key(GYM_ANNOUNCEMENTS, self.gym.pk), key)
                self.assertEqual(cache.get(key), warmed)
            items = self.list_announcements()
            self.assertEqual(
                [item["id"] for item in items],
                [str(announcement.pk)] if visible else [],
            )
            if visible:
                self.assertIsNotNone(items[0]["published_at"])
            self.assertEqual(cache_key(GYM_ANNOUNCEMENTS, self.other_gym.pk), other_key)

    def test_rollback_preserves_state_and_cached_list(self):
        announcement = self.make_announcement()
        original = GymAnnouncement.objects.values().get(pk=announcement.pk)
        self.assertEqual(self.list_announcements(), [])
        key = cache_key(GYM_ANNOUNCEMENTS, self.gym.pk)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaisesMessage(RuntimeError, "roll back publication"):
                with transaction.atomic():
                    response = self.update(announcement, {"status": "PUBLISHED"})
                    self.assertEqual(response.status_code, 200)
                    raise RuntimeError("roll back publication")
        self.assertEqual(callbacks, [])
        self.assertEqual(
            GymAnnouncement.objects.values().get(pk=announcement.pk), original
        )
        self.assertEqual(cache_key(GYM_ANNOUNCEMENTS, self.gym.pk), key)
        self.assertEqual(self.list_announcements(), [])

    def test_other_gym_owner_cannot_publish(self):
        announcement = self.make_announcement()
        self.client.force_authenticate(user=self.other_owner)
        response = self.update(announcement, {"status": "PUBLISHED"})
        self.assertEqual(response.status_code, 404)
        announcement.refresh_from_db()
        self.assertEqual(announcement.status, "DRAFT")
        self.assertIsNone(announcement.published_at)

    def test_announcement_must_belong_to_url_gym(self):
        announcement = self.make_announcement(gym=self.other_gym)
        response = self.update(announcement, {"status": "PUBLISHED"})
        self.assertEqual(response.status_code, 404)
        announcement.refresh_from_db()
        self.assertEqual(announcement.status, "DRAFT")
        self.assertIsNone(announcement.published_at)

    def test_unauthenticated_user_cannot_publish(self):
        announcement = self.make_announcement()
        self.client.force_authenticate(user=None)
        response = self.update(announcement, {"status": "PUBLISHED"})
        self.assertEqual(response.status_code, 400)
        announcement.refresh_from_db()
        self.assertEqual(announcement.status, "DRAFT")
        self.assertIsNone(announcement.published_at)

    def test_admin_can_publish(self):
        announcement = self.make_announcement()
        self.client.force_authenticate(user=self.admin)
        response = self.update(announcement, {"status": "PUBLISHED"})
        self.assertEqual(response.status_code, 200)
        announcement.refresh_from_db()
        self.assertEqual(announcement.status, "PUBLISHED")
        self.assertIsNotNone(announcement.published_at)
