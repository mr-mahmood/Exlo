# gym_subscriptions/tasks.py_compile

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from celery import shared_task

from gym_subscriptions.models import GymSubscription


@shared_task
def sweep_gym_subscriptions():
    now = timezone.now()

    stale_subscriptions = list(
        GymSubscription.objects.filter(status=GymSubscription.Status.ACTIVE)
        .filter(Q(expires_at__lte=now) | Q(remaining_visits__lte=0))
        .values_list("id", flat=True)
    )

    for subscription_id in stale_subscriptions:
        with transaction.atomic():
            subscription: GymSubscription = (
                GymSubscription.objects.select_for_update()
                .filter(
                    pk=subscription_id,
                    status=GymSubscription.Status.ACTIVE,
                )
                .first()
            )

            if subscription is None or not subscription.is_expired:
                continue

            reason = subscription.expire_reason
            subscription.expire(reason=reason)
