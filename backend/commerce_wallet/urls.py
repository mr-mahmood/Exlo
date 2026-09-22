# commerce_wallet/urls.py

from django.urls import path
from .views import WalletAPIView

app_name = "commerce_wallet"

urlpatterns = [
    path(
        "",
        WalletAPIView.as_view(),
        name="detail",
    ),
]
