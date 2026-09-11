# user_referrals/urls.py
from django.urls import path
from .views import UserReferralPIView

app_name = "user_referrals"

urlpatterns = [
    path(
        "",
        UserReferralPIView.as_view(),
        name="user-referrals",
    ),
]
