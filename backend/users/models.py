import uuid
import secrets
from django.utils import timezone
from django.db import models, transaction
from django.contrib.auth.models import AbstractUser, BaseUserManager
from core.errors import APIError, UserAccountError
from users.utils import normalize_phone


class UserManager(BaseUserManager):

    def get_user(self, user_id) -> "User":
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise APIError(UserAccountError.USER_NOT_EXIST)

    def get_user_by_phone(self, phone_number) -> "User":
        try:
            return User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            raise APIError(UserAccountError.USER_NOT_EXIST)

    def _generate_unique_referral_code(self):
        """
        Generate random, human-readable referral codes.
        Code space is around 1,073,741,824 unique referral code.
        Excludes visually ambiguous characters:
        0, O, 1, I
        """
        CHARACTERS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        LENGTH = 6

        while True:
            code = "".join(secrets.choice(CHARACTERS) for _ in range(LENGTH))
            if not User.objects.filter(referral_code=code):
                return code

    def create_user(self, phone_number, **extra_fields):
        extra_fields.setdefault("role", User.Role.USER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        user = User(
            phone_number=normalize_phone(phone_number),
            referral_code=self._generate_unique_referral_code(),
            **extra_fields,
        )

        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        user = User(
            phone_number=normalize_phone(phone_number),
            referral_code=self._generate_unique_referral_code(),
            **extra_fields,
        )

        user.set_password(password)
        user.save(using=self._db)
        return user


def user_profile_picture_path(instance, filename):
    return f"profile_pics/{uuid.uuid7().hex}.webp"


class User(AbstractUser):
    email = None
    username = None
    last_login = None

    class Gender(models.TextChoices):
        MALE = "MALE"
        FEMALE = "FEMALE"

    class Role(models.TextChoices):
        ADMIN = "ADMIN"
        USER = "USER"

    # Primary Key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
        db_index=True,
    )

    # Contact Information
    phone_number = models.CharField(
        max_length=11,
        unique=True,
    )

    # Personal Information
    first_name = models.CharField(
        max_length=255,
        null=False,
        blank=False,
    )

    last_name = models.CharField(
        max_length=255,
        null=False,
        blank=False,
    )

    profile_picture = models.ImageField(
        upload_to=user_profile_picture_path,
        null=True,
        blank=True,
        default="profile_pics/default_profile_image.png",
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )

    gender = models.CharField(
        max_length=20,
        choices=Gender.choices,
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.USER,
    )

    # Referral System
    referral_code = models.CharField(
        max_length=6,
        unique=True,
        editable=False,
    )

    # Status Flags
    is_active = models.BooleanField(
        default=True,
    )

    # Timestamps
    last_login_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects: UserManager = UserManager()

    class Meta:
        db_table = "users"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["role"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["last_login_at"]),
            models.Index(fields=["referral_code"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(phone_number__regex=r"^09[0-9]{9}$"),
                name="users_phone_ascii_mobile",
            ),
        ]

    def __str__(self):
        return f"{self.full_name}"

    @property
    def full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_admin(self):
        """Check if user is admin"""
        return bool(self.is_active and self.is_staff and self.is_superuser and self.role == User.Role.ADMIN)

    def validate_account_status(self):
        if not self.is_active:
            raise APIError(UserAccountError.USER_ACCOUNT_INACTIVE)

        return self

    def update_last_login_at(self):
        """update session last_activity_at"""
        self.last_login_at = timezone.now()
        self.save(update_fields=["last_login_at", "updated_at"])
