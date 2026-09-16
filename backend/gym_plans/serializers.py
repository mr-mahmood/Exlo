# gym_plans/serializers.py

from rest_framework import serializers
from .models import GymMembershipPlan
from core.errors import APIError, GymPlansError
from gym.serializers import GymBasicSerializer


class GymMembershipPlanSerializer(serializers.ModelSerializer):
    gym = GymBasicSerializer(read_only=True)

    class Meta:
        model = GymMembershipPlan
        fields = [
            "id",
            "name",
            "gym",
            "description",
            "duration_months",
            "visit_limit",
            "is_active",
            "price",
        ]
        read_only_fields = [
            "id",
            "gym",
        ]

    def validate_duration_months(self, value):
        if value < 0:
            raise APIError(GymPlansError.INVALID_DURATION)
        return value

    def validate_visit_limit(self, value):
        if value < 0:
            raise APIError(GymPlansError.INVALID_VISIT_LIMIT)
        return value

    def validate_price(self, value):
        if value < 0:
            raise APIError(GymPlansError.INVALID_PRICE)
        return value
