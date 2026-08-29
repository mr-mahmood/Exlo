from django.urls import path, include
from users.views import (
    UserSignupAPIView,
    UserProfilePIView,
    PhoneChangeOldRequestAPIView,
    PhoneChangeOldVerifyAPIView,
    PhoneChangeNewRequestAPIView,
    PhoneChangeNewVerifyAPIView,
)

app_name = "users"

urlpatterns = [
    path(
        "signup/",
        UserSignupAPIView.as_view(),
        name="user-signup",
    ),
    path(
        "profile/",
        UserProfilePIView.as_view(),
        name="dashboard",
    ),
    path(
        "phone-change/old/request/",
        PhoneChangeOldRequestAPIView.as_view(),
        name="phone-change-old-request",
    ),
    path(
        "phone-change/old/verify/",
        PhoneChangeOldVerifyAPIView.as_view(),
        name="phone-change-old-verify",
    ),
    path(
        "phone-change/new/request/",
        PhoneChangeNewRequestAPIView.as_view(),
        name="phone-change-new-request",
    ),
    path(
        "phone-change/new/verify/",
        PhoneChangeNewVerifyAPIView.as_view(),
        name="phone-change-new-verify",
    ),
]
