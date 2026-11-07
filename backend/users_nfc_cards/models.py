# users_nfc_cards/models.py

import uuid
from django.core.cache import cache
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

    def find_or_assign_card(self, uid, gym_id) -> tuple["UserNfcCard", bool]:

        if not isinstance(uid, str) or not uid.strip():
            raise APIError(UserNfcCardError.INVALID_UID)
        uid = uid.strip()

        try:
            return self.get(uid=uid), False
        except UserNfcCard.DoesNotExist:
            pass

        key = f"nfc_card_assign_{gym_id}"
        user_id = cache.get(key)
        if user_id is None:
            raise APIError(UserNfcCardError.CARD_NOT_FOUND)

        user: User = User.objects.get_user(user_id)
        user.validate_account_status()
        card = self.assign_card(user=user, uid=uid)
        cache.delete(key)
        return card, True

    def assign_card(self, user, uid) -> "UserNfcCard":

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
                return self.create(user=user, uid=uid)
            except IntegrityError:
                # Race: another request claimed this UID first.
                raise APIError(UserNfcCardError.CARD_ALREADY_ASSIGNED)


class UserNfcCard(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="nfc_card",
    )

    uid = models.CharField(
        max_length=255,
        unique=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects: UserNfcCardManager = UserNfcCardManager()

    class Meta:
        db_table = "user_nfc_card"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.uid} -> {self.user}"
