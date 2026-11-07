# gym_subscriptions/models.py

import uuid
from datetime import timedelta
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from commerce_products.models import CommerceProduct
from users.models import User
from gym_plans.models import GymMembershipPlan
from gym.models import Gym
from commerce_orders.models import OrderItem
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
            subscription = self._promote_next_for_gym(subscriber, gym)
        if subscription is None:
            raise APIError(GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION)

        subscription.remaining_visits -= 1
        subscription.save(update_fields=["remaining_visits", "updated_at"])

        if subscription.remaining_visits <= 0:
            subscription.expire(reason=subscription.expire_reason)
            self._promote_next_for_gym(subscriber, gym)

        invalidate_user_subscription_caches(subscriber.id, subscription.id)
        return subscription

    # This function caller must prefetch the product chain, before calling this function
    def create_subscription(self, subscriber, order_item: OrderItem):
        if order_item.item_type != CommerceProduct.ProductType.GYM_MEMBERSHIP:
            raise APIError(GymSubscriptionError.INVALID_ORDER_ITEM)

        plan: GymMembershipPlan = order_item.commerce_product.gym_membership_plan

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
                active.expires_at > timezone.now() + timedelta(days=7)
                and active.remaining_visits > 2
            ):
                raise APIError(GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS)

            subscription = self.create(
                subscriber=subscriber,
                plan=plan,
                order_item=order_item,
                status=GymSubscription.Status.PENDING,
                remaining_visits=plan.visit_limit,
                duration_months=plan.duration_months,
            )

            if active is None:
                self._activate_subscription(subscription)

            invalidate_user_subscription_caches(subscriber.id, subscription.id)
            return subscription

    def cancel_subscription(self, subscription):
        with transaction.atomic():
            subscriber_id = subscription.subscriber_id
            subscriber = User.objects.select_for_update().get(pk=subscriber_id)
            subscription: GymSubscription = self.select_for_update().get(
                pk=subscription.pk
            )

            if subscription.status in (
                GymSubscription.Status.EXPIRED,
                GymSubscription.Status.CANCELLED,
            ):
                return subscription

            was_active_sub = subscription.status == GymSubscription.Status.ACTIVE
            subscription.cancel()
            if was_active_sub:
                self._promote_next_for_gym(subscriber, subscription.gym)

            return subscription

    def _promote_next_for_gym(self, subscriber, gym) -> "GymSubscription | None":
        if self._has_active_subscription(subscriber, gym):
            return None

        next_subscription = (
            self.select_for_update(of=("self",))
            .filter(
                subscriber=subscriber,
                status=GymSubscription.Status.PENDING,
                gym=gym,
            )
            .order_by("created_at")
            .first()
        )

        if next_subscription is None:
            return None

        try:
            self._activate_subscription(next_subscription)
        except IntegrityError as e:
            if "unique_active_subscription_per_user_gym" in str(e):
                return None
            raise

        return next_subscription

    def _activate_subscription(self, subscription: "GymSubscription"):

        if self._has_active_subscription(
            subscription.subscriber,
            subscription.gym,
            subscription.pk,
        ):
            raise APIError(GymSubscriptionError.ACTIVE_SUBSCRIPTION_EXISTS)

        subscription.activate()
        return subscription

    def _has_active_subscription(self, subscriber, gym, exclude_pk=None):
        qs = self.filter(
            subscriber=subscriber,
            gym=gym,
            status=GymSubscription.Status.ACTIVE,
        )

        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)

        return qs.exists()


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

    order_item = models.OneToOneField(
        OrderItem,
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

    def activate(self):
        if self.status == self.Status.PENDING:
            now = timezone.now()

            self.status = self.Status.ACTIVE
            self.started_at = now
            self.expires_at = now + relativedelta(months=self.duration_months)
            self.end_reason = None
            self.cancelled_at = None

            self.save(
                update_fields=[
                    "status",
                    "started_at",
                    "expires_at",
                    "end_reason",
                    "cancelled_at",
                    "updated_at",
                ]
            )
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
            self.save(
                update_fields=["status", "end_reason", "cancelled_at", "updated_at"]
            )
            invalidate_user_subscription_caches(self.subscriber_id, self.pk)
