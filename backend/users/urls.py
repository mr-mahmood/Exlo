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
    # Phone change flow (4 steps)
    path(
        "phone-change/",
        include(
            [
                path(
                    "old/request/",
                    PhoneChangeOldRequestAPIView.as_view(),
                    name="phone-change-old-request",
                ),
                path(
                    "old/verify/",
                    PhoneChangeOldVerifyAPIView.as_view(),
                    name="phone-change-old-verify",
                ),
                path(
                    "new/request/",
                    PhoneChangeNewRequestAPIView.as_view(),
                    name="phone-change-new-request",
                ),
                path(
                    "new/verify/",
                    PhoneChangeNewVerifyAPIView.as_view(),
                    name="phone-change-new-verify",
                ),
            ]
        ),
    ),
]
