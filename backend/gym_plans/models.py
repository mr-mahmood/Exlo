# gym_plans/models.py

from django.db import models
from django.db.models import QuerySet
from django.utils import timezone
from commerce_products.models import CommerceProduct
from gym.models import Gym


class GymMembershipPlanManager(models.Manager):

    def create_plan(self, **extra_fields) -> "GymMembershipPlan":
        # Create commerce product first
        commerce_product = CommerceProduct.objects.create(
            product_type=CommerceProduct.ProductType.GYM_MEMBERSHIP
        )

        # Create the plan with commerce_product as id
        plan = self.model(
            id=commerce_product,
            **extra_fields,
        )
        plan.save(using=self._db)
        return plan

    def get_plan(self, plan_id, gym=None, active_only=True) -> "GymMembershipPlan":
        try:
            queryset = self.filter(id=plan_id)

            if gym:
                queryset = queryset.filter(gym=gym)

            if active_only:
                queryset = queryset.filter(is_active=True)

            return queryset.get()
        except GymMembershipPlan.DoesNotExist:
            from core.errors import APIError, GymPlansError

            raise APIError(GymPlansError.PLAN_NOT_FOUND)

    def get_gym_plans(self, gym, active_only=True) -> QuerySet["GymMembershipPlan"]:
        queryset = self.filter(gym=gym)

        if active_only:
            queryset = queryset.filter(is_active=True)

        return queryset


class GymMembershipPlan(models.Model):

    # Primary key is the commerce_product_id (One-to-One)
    id = models.OneToOneField(
        CommerceProduct,
        on_delete=models.CASCADE,
        primary_key=True,
        editable=False,
        related_name="gym_membership_plan",
    )

    gym = models.ForeignKey(
        Gym,
        on_delete=models.CASCADE,
        related_name="membership_plans",
    )

    name = models.CharField(max_length=255)
    description = models.TextField()
    duration_month = models.IntegerField(default=1)
    visit_limit = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Custom manager
    objects: GymMembershipPlanManager = GymMembershipPlanManager()

    class Meta:
        db_table = "gym_membership_plans"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["gym"]),
            models.Index(fields=["gym", "is_active"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["deleted_at"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.gym.name}"

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    @property
    def is_available(self):
        return self.is_active and not self.is_deleted

    def delete(self):
        if self.is_available:
            self.deleted_at = timezone.now()
            self.is_active = False
            self.save(update_fields=["deleted_at", "is_active", "updated_at"])
