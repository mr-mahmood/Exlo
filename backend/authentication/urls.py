from django.urls import path
from authentication.views import RefreshAPIView, LogoutAPIView, LoginRequestApiView, LoginVerifyApiView

app_name = 'authentication'

urlpatterns = [
    path('login/request/', LoginRequestApiView.as_view(), name='login-request'),
    path('login/verify/', LoginVerifyApiView.as_view(), name='login-verify'),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("refresh/", RefreshAPIView.as_view(), name="refresh"),
]
