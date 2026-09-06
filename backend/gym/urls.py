# gym/urls.py

from django.urls import path
from .views import (
    GymListAPIView,
    GymDetailAPIView,
    GymCreateAPIView,
    GymUpdateAPIView,
    GymDeleteAPIView,
)

app_name = "gym"

urlpatterns = [
    path("", GymListAPIView.as_view(), name="list"),
    path("create/", GymCreateAPIView.as_view(), name="create"),
    path("<uuid:gym_id>/", GymDetailAPIView.as_view(), name="detail"),
    path("<uuid:gym_id>/update/", GymUpdateAPIView.as_view(), name="update"),
    path("<uuid:gym_id>/delete/", GymDeleteAPIView.as_view(), name="delete"),
]
