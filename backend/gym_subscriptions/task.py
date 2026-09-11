# gym_subscriptions/tasks.py

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import GymSubscription


@shared_task
def sweep_gym_subscriptions():
    now = timezone.now()

    stale_ids = (
        GymSubscription.objects.filter(status=GymSubscription.Status.ACTIVE)
        .filter(Q(expires_at__lte=now) | Q(remaining_visits__lte=0))
        .values_list("id", flat=True)
    )

    for subscription_id in stale_ids.iterator():
        with transaction.atomic():
            subscription: GymSubscription = (
                GymSubscription.objects.select_for_update()
                .filter(
                    pk=subscription_id,
                    status=GymSubscription.Status.ACTIVE,
                )
                .first()
            )  # type: ignore

            if subscription is None or not subscription.is_expired:
                continue

            subscription.expire(reason=subscription.expire_reason)

            GymSubscription.objects.promote_next(subscription.subscriber)
