# gym_subscriptions/models.py

import uuid
from django.db import models, transaction
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from users.models import User
from gym_plans.models import GymMembershipPlan
from commerce_orders.models import OrderItem
from core.errors import APIError, GymSubscriptionError


class GymSubscriptionsManager(models.Manager):

    def check_in(self, subscriber, gym):
        error = None

        with transaction.atomic():
            subscription: GymSubscription = (
                self.select_for_update()
                .select_related("plan")
                .filter(subscriber=subscriber, status=GymSubscription.Status.ACTIVE)
                .first()
            )  # type: ignore

            if subscription is None:
                error = APIError(GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION)

            elif subscription.is_expired:
                subscription.expire(reason=subscription.expire_reason)

                subscription = self.promote_next(subscriber)  # type: ignore

                if subscription is None or not subscription.is_active:
                    error = APIError(GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION)

            if error is None:
                if subscription.plan.gym_id != gym.id:
                    error = APIError(GymSubscriptionError.WRONG_GYM)
                else:
                    subscription.remaining_visits -= 1

                    subscription.save(
                        update_fields=[
                            "remaining_visits",
                            "updated_at",
                        ]
                    )

                    if subscription.remaining_visits <= 0:
                        subscription.expire(
                            reason=subscription.expire_reason,
                        )
                        self.promote_next(subscriber)

        if error is not None:
            raise error

        return subscription

    def activate_subscription(self, subscription: "GymSubscription"):
        has_active_subscription = (
            self.filter(
                subscriber=subscription.subscriber,
                status=GymSubscription.Status.ACTIVE,
            )
            .exclude(pk=subscription.pk)
            .exists()
        )

        if has_active_subscription:
            raise APIError(GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS)

        subscription.activate()
        return subscription

    def promote_next(self, subscriber) -> "GymSubscription | None":
        next_subscription = (
            self.filter(
                subscriber=subscriber,
                status=GymSubscription.Status.PENDING,
            )
            .order_by("created_at")
            .first()
        )

        if next_subscription is not None:
            self.activate_subscription(next_subscription)

        return next_subscription


class GymSubscription(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"

    class EndReason(models.TextChoices):
        TIME = "TIME", "Time expired"
        VISITS = "VISITS", "Visits exhausted"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    subscriber = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="gym_subscriptions",
    )

    plan = models.ForeignKey(
        GymMembershipPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.PROTECT,
        related_name="gym_subscriptions",
    )

    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.PENDING,
    )

    end_reason = models.CharField(
        max_length=50,
        choices=EndReason.choices,
        null=True,
        blank=True,
    )

    remaining_visits = models.PositiveIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: GymSubscriptionsManager = GymSubscriptionsManager()

    class Meta:
        db_table = "gym_subscriptions"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscriber"],
                condition=models.Q(status="ACTIVE"),
                name="unique_active_subscription_per_user",
            ),
        ]

    # ---------- properties ----------
    @property
    def is_expired_by_time(self) -> bool:
        return self.expires_at is not None and self.expires_at <= timezone.now()

    @property
    def is_expired_by_visits(self) -> bool:
        return self.remaining_visits <= 0

    @property
    def is_expired(self) -> bool:
        return self.is_expired_by_time or self.is_expired_by_visits

    @property
    def expire_reason(self):
        if self.is_expired_by_time:
            return self.EndReason.TIME
        if self.is_expired_by_visits:
            return self.EndReason.VISITS
        return None

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE and not self.is_expired

    def activate(self):
        if self.status == self.Status.PENDING:
            now = timezone.now()

            self.status = self.Status.ACTIVE
            self.started_at = now
            self.expires_at = now + relativedelta(months=self.plan.duration_month)
            self.remaining_visits = self.plan.visit_limit
            self.end_reason = None
            self.cancelled_at = None

            self.save(
                update_fields=[
                    "status",
                    "started_at",
                    "expires_at",
                    "remaining_visits",
                    "end_reason",
                    "cancelled_at",
                    "updated_at",
                ]
            )

    def expire(self, reason):
        if self.status == self.Status.ACTIVE:
            self.status = self.Status.EXPIRED
            self.end_reason = reason
            self.save(update_fields=["status", "end_reason", "updated_at"])

    def cancel(self):
        if self.status in (self.Status.EXPIRED, self.Status.CANCELLED):
            return

        self.status = self.Status.CANCELLED
        self.end_reason = self.EndReason.CANCELLED
        self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "end_reason", "cancelled_at", "updated_at"])
        GymSubscription.objects.promote_next(self.subscriber)
