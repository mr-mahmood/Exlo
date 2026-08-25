# user_referrals/serializers.py
from rest_framework import serializers
from users.models import User
from .models import Referral


class ReferredUserSerializer(serializers.ModelSerializer):
    """Serializer for referred user"""

    class Meta:
        model = User
        fields = [
            "phone_number",
            "first_name",
            "last_name",
        ]
        read_only_fields = [
            "phone_number",
            "first_name",
            "last_name",
        ]


class UserReferralSerializer(serializers.ModelSerializer):
    """Serializer for referral with nested user details"""

    referred_user = ReferredUserSerializer(read_only=True)

    class Meta:
        model = Referral
        fields = [
            "referred_user",
            "referred_at",
        ]
        read_only_fields = [
            "referred_user",
            "referred_at",
        ]
