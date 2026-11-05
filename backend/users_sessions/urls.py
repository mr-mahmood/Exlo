from django.urls import path, include
from .views import UserSessionListAPIView, UserSessionDeleteAPIView

app_name = "user_sessions"

urlpatterns = [
    path(
        "",
        UserSessionListAPIView.as_view(),
        name="user-sessions",
    ),
    path(
        "delete/",
        UserSessionDeleteAPIView.as_view(),
        name="user-session-delete",
    ),
]
