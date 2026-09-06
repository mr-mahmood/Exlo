# user_referrals/serializers.py
from rest_framework import serializers
from users.serializers import UserBasicSerializer
from .models import Referral


class UserReferralSerializer(serializers.ModelSerializer):
    referred_user = UserBasicSerializer(read_only=True)

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
