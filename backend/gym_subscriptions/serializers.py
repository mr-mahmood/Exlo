# gym_subscriptions/serializers.py
from rest_framework import serializers

from gym_plans.serializers import GymMembershipPlanSerializer
from .models import GymSubscription
from gym.serializers import GymBasicSerializer


class GymSubscriptionReadSerializer(serializers.ModelSerializer):
    plan = GymMembershipPlanSerializer(read_only=True)
    gym = GymBasicSerializer(source="plan.gym", read_only=True)

    class Meta:
        model = GymSubscription
        fields = [
            "id",
            "plan",
            "gym",
            "status",
            "end_reason",
            "initial_visits",
            "remaining_visits",
            "started_at",
            "expires_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields
