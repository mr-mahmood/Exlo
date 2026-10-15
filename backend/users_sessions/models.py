import uuid
from django.db import models
from users.models import User
from django.utils import timezone


class Session(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    user = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="sessions",
    )

    session_id = models.UUIDField(
        unique=True,
        default=uuid.uuid7,
        editable=False,
    )

    # Device Information
    ip_address = models.CharField(max_length=45)
    user_agent = models.CharField(max_length=255)

    # Timestamps
    last_activity_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session_id"]),
            models.Index(fields=["session_id", "user"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.ip_address}"

    @classmethod
    def create_session(cls, user, request):
        """Create a new session from request data (IP and User-Agent are required)"""

        # Get IP
        ip = request.META.get("HTTP_X_FORWARDED_FOR")
        if ip:
            ip = ip.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")

        if not ip:
            ip = "0.0.0.0"

        # Get User Agent
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        if not user_agent:
            user_agent = "Unknown Client"

        return cls.objects.create(
            user=user,
            session_id=uuid.uuid7(),
            ip_address=ip[:45],
            user_agent=user_agent[:255],
            last_activity_at=timezone.now(),
        )

    def update_last_activity_at(self):
        """update session last_activity_at"""
        self.last_activity_at = timezone.now()
        self.save(update_fields=["last_activity_at", "updated_at"])
