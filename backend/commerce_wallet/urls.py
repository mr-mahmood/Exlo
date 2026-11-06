# commerce_wallet/urls.py

from django.urls import path
from .views import WalletAPIView, WalletTopUpAPIView, WalletTopUpCallbackAPIView

app_name = "commerce_wallet"

urlpatterns = [
    path("", WalletAPIView.as_view(), name="detail"),
    path("top-up/", WalletTopUpAPIView.as_view(), name="top-up"),
    path("callback/", WalletTopUpCallbackAPIView.as_view(), name="callback"),
]
