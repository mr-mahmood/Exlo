# gym_visits/serializers.py

from rest_framework import serializers

from core.errors import APIError, GymVisitsError
from gym_visits.models import GymVisit


class CheckInSerializer(serializers.Serializer):
    method = serializers.CharField()

    def validate_method(self, value):
        if value not in GymVisit.Method.values:
            raise APIError(GymVisitsError.INVALID_METHOD)
        return value


class CheckOutSerializer(serializers.Serializer):
    method = serializers.CharField()

    def validate_method(self, value):
        if value not in GymVisit.Method.values:
            raise APIError(GymVisitsError.INVALID_METHOD)
        return value
