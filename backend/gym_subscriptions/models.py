# gym_subscriptions/models.py

import uuid
from datetime import timedelta
from django.db import models, transaction
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from commerce_products.models import CommerceProduct
from users.models import User
from gym_plans.models import GymMembershipPlan
from gym.models import Gym
from commerce_orders.models import Order
from core.errors import APIError, GymSubscriptionError
from core.cache import invalidate_user_subscription_caches


class GymSubscriptionsManager(models.Manager):
    def get_subscription(self, subscription_id, subscriber):
        try:
            return self.select_related(
                "plan",
                "plan__gym",
            ).get(
                pk=subscription_id,
                subscriber=subscriber,
            )
        except GymSubscription.DoesNotExist:
            raise APIError(GymSubscriptionError.SUBSCRIPTION_NOT_FOUND)

    def consume_visit(self, subscriber, gym):
        subscriber = User.objects.select_for_update().get(pk=subscriber.pk)

        subscription: GymSubscription = (
            self.select_for_update(of=("self",))
            .filter(
                subscriber=subscriber,
                gym=gym,
                status=GymSubscription.Status.ACTIVE,
            )
            .first()
        )

        if subscription is not None and subscription.is_expired:
            subscription.expire(reason=subscription.expire_reason)
            subscription = None

        if subscription is None:
            subscription = self._activate_pending_for_check_in(subscriber, gym)
        if subscription is None or not subscription.is_active:
            raise APIError(GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION)

        subscription.consume_visit()
        invalidate_user_subscription_caches(subscriber.id, subscription.id)
        return subscription

    def create_subscription(self, subscriber, order: Order):
        if order.commerce_product.product_type != CommerceProduct.ProductType.GYM_MEMBERSHIP:
            raise APIError(GymSubscriptionError.INVALID_ORDER_ITEM)

        plan: GymMembershipPlan = order.commerce_product.gym_membership_plan

        with transaction.atomic():
            subscriber = User.objects.select_for_update().get(pk=subscriber.pk)

            active: GymSubscription = (
                self.select_for_update(of=("self",))
                .filter(
                    subscriber=subscriber,
                    gym_id=plan.gym_id,
                    status=GymSubscription.Status.ACTIVE,
                )
                .first()
            )
            if active is not None and active.is_expired:
                active.expire(reason=active.expire_reason)
                active = None

            if self.filter(
                subscriber=subscriber,
                gym_id=plan.gym_id,
                status=GymSubscription.Status.PENDING,
            ).exists():
                raise APIError(GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS)

            if active is not None and (
                active.expires_at > timezone.now() + timedelta(days=7) and active.remaining_visits > 2
            ):
                raise APIError(GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS)

            subscription = self.create(
                subscriber=subscriber,
                plan=plan,
                order=order,
                status=GymSubscription.Status.PENDING,
                initial_visits=plan.visit_limit,
                remaining_visits=plan.visit_limit,
                duration_months=plan.duration_months,
            )

            invalidate_user_subscription_caches(subscriber.id, subscription.id)
            return subscription

    def _activate_pending_for_check_in(self, subscriber, gym) -> "GymSubscription | None":
        # The caller holds the user lock and has already ruled out an active subscription.
        try:
            subscription = self.select_for_update(of=("self",)).get(
                subscriber=subscriber,
                gym=gym,
                status=GymSubscription.Status.PENDING,
            )
        except self.model.DoesNotExist:
            return None

        subscription.activate()
        return subscription


class GymSubscription(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        ACTIVE = "ACTIVE"
        EXPIRED = "EXPIRED"
        CANCELLED = "CANCELLED"

    class EndReason(models.TextChoices):
        TIME = "TIME"
        VISITS = "VISITS"
        CANCELLED = "CANCELLED"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    subscriber = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="my_subscriptions",
        editable=False,
    )

    plan = models.ForeignKey(
        GymMembershipPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        editable=False,
    )

    gym = models.ForeignKey(
        Gym,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        editable=False,
    )

    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="gym_subscription",
        editable=False,
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

    duration_months = models.PositiveIntegerField(default=1)
    initial_visits = models.PositiveIntegerField(default=0, editable=False)
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

        indexes = [
            models.Index(fields=["subscriber", "status"]),
            models.Index(fields=["expires_at", "remaining_visits"]),
            models.Index(fields=["created_at"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["subscriber", "gym"],
                condition=models.Q(status="ACTIVE"),
                name="unique_active_subscription_per_user_gym",
            ),
            models.UniqueConstraint(
                fields=["subscriber", "gym"],
                condition=models.Q(status="PENDING"),
                name="unique_pending_subscription_per_user_gym",
            ),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.gym_id = self.plan.gym_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subscriber_id} - {self.plan_id} [{self.status}]"

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

    @property
    def is_refundable(self) -> bool:
        condition1 = self.status in (self.Status.PENDING, self.Status.ACTIVE)
        condition2 = self.remaining_visits == self.initial_visits
        condition3 = self.created_at <= timezone.now() < (self.created_at + timedelta(hours=48))
        return condition1 and condition2 and condition3

    def consume_visit(self):
        self.remaining_visits -= 1
        self.save(update_fields=["remaining_visits", "updated_at"])
        if self.remaining_visits == 0:
            self.expire(reason=self.expire_reason)

    def activate(self):
        if self.status == self.Status.PENDING:
            now = timezone.now()

            self.status = self.Status.ACTIVE
            self.started_at = now
            self.expires_at = now + relativedelta(months=self.duration_months)
            self.end_reason = None
            self.cancelled_at = None

            self.save(update_fields=["status", "started_at", "expires_at", "end_reason", "cancelled_at", "updated_at"])
            invalidate_user_subscription_caches(self.subscriber_id, self.pk)

    def expire(self, reason):
        if self.status == self.Status.ACTIVE:
            self.status = self.Status.EXPIRED
            self.end_reason = reason
            self.save(update_fields=["status", "end_reason", "updated_at"])
            invalidate_user_subscription_caches(self.subscriber_id, self.pk)

    def cancel(self):
        if self.status in (self.Status.PENDING, self.Status.ACTIVE):
            self.status = self.Status.CANCELLED
            self.end_reason = self.EndReason.CANCELLED
            self.cancelled_at = timezone.now()
            self.save(update_fields=["status", "end_reason", "cancelled_at", "updated_at"])
            invalidate_user_subscription_caches(self.subscriber_id, self.pk)
