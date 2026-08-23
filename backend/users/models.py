import uuid
import secrets
from django.utils import timezone
from django.db import models, transaction
from django.contrib.auth.models import AbstractUser, BaseUserManager
from core.errors import APIError, UserAccountError


class UserManager(BaseUserManager):

    def _generate_unique_referral_code(self):
        """
        Generate random, human-readable referral codes.
        Code space is around 1,073,741,824 unique referral code.
        Excludes visually ambiguous characters:
        0, O, 1, I
        """
        while True:
            CHARACTERS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
            LENGTH = 6

            code = "".join(secrets.choice(CHARACTERS) for _ in range(LENGTH))

            if not self.model.objects.filter(referral_code=code).exists():
                return code

    def create_user(self, phone_number, **extra_fields):
        extra_fields.setdefault("role", User.Role.USER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        with transaction.atomic():

            user = self.model(
                phone_number=phone_number,
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

        with transaction.atomic():
            user = self.model(
                phone_number=phone_number,
                referral_code=self._generate_unique_referral_code(),
                **extra_fields,
            )

            user.set_password(password)
            user.save(using=self._db)

            return user


class User(AbstractUser):
    email = None
    username = None
    last_login = None

    class Gender(models.TextChoices):
        MALE = "MALE", "Male"
        FEMALE = "FEMALE", "Female"

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        USER = "USER", "User"

    # Primary Key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
    )

    # Contact Information
    phone_number = models.CharField(
        max_length=11,
        unique=True,
    )

    # Personal Information
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)

    profile_picture_url = models.ImageField(
        upload_to="profile_pics/",
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
    )

    # Status Flags
    is_active = models.BooleanField(
        default=True,
    )

    is_blocked = models.BooleanField(
        default=False,
    )

    # Timestamps
    last_login_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    blocked_at = models.DateTimeField(
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

    # Custom manager
    objects: UserManager = UserManager()

    class Meta:
        db_table = "users"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=[
                    "is_active",
                    "is_blocked",
                ],
                name="users_status_idx",
            ),
            models.Index(fields=["role"], name="users_role_idx"),
            models.Index(fields=["created_at"], name="users_created_idx"),
            models.Index(fields=["last_login_at"], name="users_login_idx"),
            models.Index(fields=["referral_code"], name="referral_code_idx"),
        ]

    def __str__(self):
        return f"{self.full_name}"

    @property
    def full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_user_active(self):
        """Check if user can access the system at all"""
        return self.is_active and not self.is_blocked

    def validate_account_status(self):
        """
        Validate user account status.
        Raises appropriate errors if account is not in good standing.
        """

        if not self.is_active:
            raise APIError(UserAccountError.USER_ACCOUNT_INACTIVE)

        if self.is_blocked:
            raise APIError(UserAccountError.USER_ACCOUNT_BLOCKED)

        return self

    def block(self):
        """Block the user."""
        self.is_blocked = True
        self.is_active = False
        self.blocked_at = timezone.now()
        self.save(update_fields=["is_blocked", "is_active", "blocked_at", "updated_at"])

    def unblock(self):
        """Unblock the user."""
        self.is_blocked = False
        self.is_active = True
        self.blocked_at = None
        self.save(update_fields=["is_blocked", "is_active", "blocked_at", "updated_at"])

    def update_last_login_at(self):
        """update session last_activity_at"""
        self.last_login_at = timezone.now()
        self.save(update_fields=["last_login_at", "updated_at"])
