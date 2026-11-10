# commerce_wallet/serializers.py

from rest_framework import serializers
from commerce_wallet.models import Wallet
from core.errors import APIError, WalletError


class WalletSerializer(serializers.ModelSerializer):

    class Meta:
        model = Wallet
        fields = ["balance", "updated_at"]
        read_only_fields = fields
