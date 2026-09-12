# gym_subscriptions/serializers.py
from rest_framework import serializers

from gym_plans.serializers import GymMembershipPlanSerializer
from .models import GymSubscription


class GymSubscriptionReadSerializer(serializers.ModelSerializer):
    plan = GymMembershipPlanSerializer(read_only=True)

    class Meta:
        model = GymSubscription
        fields = [
            "id",
            "plan",
            "status",
            "end_reason",
            "remaining_visits",
            "started_at",
            "expires_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields
