# gym_plans/serializers.py

from rest_framework import serializers
from .models import GymMembershipPlan
from core.errors import APIError, GymPlansError


class GymMembershipPlanSerializer(serializers.ModelSerializer):

    class Meta:
        model = GymMembershipPlan
        fields = [
            "id",
            "name",
            "description",
            "duration_month",
            "visit_limit",
            "is_active",
            "price",
        ]
        read_only_fields = ["id"]

    def validate_duration_month(self, value):
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
