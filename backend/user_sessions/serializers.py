from rest_framework import serializers
from .models import Session


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = [
            "session_id",
            "ip_address",
            "user_agent",
            "last_activity_at",
        ]

        read_only_fields = [
            "session_id",
            "ip_address",
            "user_agent",
            "last_activity_at",
        ]
