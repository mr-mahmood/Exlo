from django.urls import path, include
from .views import UserSessionPIView

app_name = "user_sessions"

urlpatterns = [
    path(
        "",
        UserSessionPIView.as_view(),
        name="user-sessions",
    ),
]
