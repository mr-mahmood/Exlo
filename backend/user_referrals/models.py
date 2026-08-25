import uuid
from django.db import models
from core.errors import APIError, ReferralError
from users.models import User
from django.utils import timezone


class Referral(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    referrer = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="recruits",
    )

    referred_user = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="sponsor",
    )

    referred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_referrals"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["referred_user"], name="referral_referred_user_idx"),
            models.Index(fields=["referrer"], name="referral_referrer_idx"),
            models.Index(
                fields=["referred_user", "referrer"], name="referral_unique_idx"
            ),
        ]
        unique_together = [["referrer", "referred_user"]]

    def save(self, *args, **kwargs):
        """Prevent self-referrals before saving"""
        if self.referrer == self.referred_user:
            raise APIError(ReferralError.SELF_REFERRAL_NOT_ALLOWED)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.referred_user} referred by {self.referrer}"
