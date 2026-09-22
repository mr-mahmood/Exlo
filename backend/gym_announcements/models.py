# gym_announcements/models.py

import uuid
from django.db import models
from django.utils import timezone
from users.models import User
from gym.models import Gym


class GymAnnouncementManager(models.Manager):

    def get_announcement(self, announcement_id, gym=None) -> "GymAnnouncement":
        try:
            queryset = self.filter(id=announcement_id)

            if gym:
                queryset = queryset.filter(gym=gym)

            return queryset.get()
        except GymAnnouncement.DoesNotExist:
            from core.errors import APIError, GymAnnouncementError

            raise APIError(GymAnnouncementError.ANNOUNCEMENT_NOT_FOUND)


class GymAnnouncement(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        PUBLISHED = "PUBLISHED"
        ARCHIVED = "ARCHIVED"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    gym = models.ForeignKey(
        to=Gym,
        on_delete=models.CASCADE,
        related_name="announcements",
    )

    author = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="gym_announcements",
    )

    title = models.CharField(max_length=255)
    content = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    archived_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom manager
    objects: GymAnnouncementManager = GymAnnouncementManager()

    class Meta:
        db_table = "gym_announcement"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["author", "gym"]),
            models.Index(fields=["gym", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"announcement: {self.title}, Gym: {self.gym.name}, User: {self.author.full_name}"

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    @property
    def is_draft(self):
        return self.status == self.Status.DRAFT

    @property
    def is_archived(self):
        return self.status == self.Status.ARCHIVED

    def publish(self):
        if self.status == self.Status.DRAFT:
            self.status = self.Status.PUBLISHED
            self.published_at = timezone.now()
            self.save(update_fields=["published_at", "status", "updated_at"])

    def archive(self):
        if self.status != self.Status.ARCHIVED:
            self.status = self.Status.ARCHIVED
            self.archived_at = timezone.now()
            self.save(update_fields=["archived_at", "status", "updated_at"])
