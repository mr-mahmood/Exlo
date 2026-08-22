from django.urls import path
from users.views import UserSignupAPIView, UserProfilePIView

app_name = 'users'

urlpatterns = [
    path('signup/', UserSignupAPIView.as_view(), name='user-signup'),
    path("profile/", UserProfilePIView.as_view(), name="dashboard"),
]
