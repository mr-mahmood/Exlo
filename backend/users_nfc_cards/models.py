# users_nfc_cards/models.py

import uuid
from django.db import IntegrityError, models, transaction
from core.errors import APIError, UserNfcCardError
from users.models import User


class UserNfcCardManager(models.Manager):

    def find_card(self, uid) -> "UserNfcCard":
        if not isinstance(uid, str) or not uid.strip():
            raise APIError(UserNfcCardError.INVALID_UID)

        uid = uid.strip()
        try:
            return self.get(uid=uid)
        except UserNfcCard.DoesNotExist:
            raise APIError(UserNfcCardError.CARD_NOT_FOUND)

    def assign_card(self, user, uid, assigned_by=None) -> "UserNfcCard":
        if not isinstance(uid, str) or not uid.strip():
            raise APIError(UserNfcCardError.INVALID_UID)

        uid = uid.strip()
        # UID is already claimed by a different user?
        if self.filter(uid=uid).exclude(user=user).exists():
            raise APIError(UserNfcCardError.CARD_ALREADY_ASSIGNED)

        with transaction.atomic():
            # Serialize concurrent assignments for the same user.
            User.objects.select_for_update().get(pk=user.pk)

            # Replace any existing card for this user.
            self.filter(user=user).delete()

            try:
                return self.create(user=user, uid=uid, assigned_by=assigned_by)
            except IntegrityError:
                # Race: another request claimed this UID first.
                raise APIError(UserNfcCardError.CARD_ALREADY_ASSIGNED)


class UserNfcCard(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.OneToOneField(
        User,
        on_delete=models.PROTECT,
        related_name="nfc_card",
    )

    uid = models.CharField(
        max_length=255,
        unique=True,
    )

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="assigned_nfc_cards",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects: UserNfcCardManager = UserNfcCardManager()

    class Meta:
        db_table = "user_nfc_card"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["assigned_by"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.uid} -> {self.user}"
