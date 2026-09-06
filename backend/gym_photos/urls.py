# gym_photos/urls.py

from django.urls import path
from .views import (
    GymPhotosAPIView,
    GymPhotoCreateAPIView,
    GymPhotoDeleteAPIView,
)

app_name = "gym_photos"

urlpatterns = [
    path(
        "<uuid:gym_id>/photos/",
        GymPhotosAPIView.as_view(),
        name="list",
    ),
    path(
        "<uuid:gym_id>/photos/create/",
        GymPhotoCreateAPIView.as_view(),
        name="create",
    ),
    path(
        "<uuid:gym_id>/photos/<uuid:photo_id>/delete/",
        GymPhotoDeleteAPIView.as_view(),
        name="delete",
    ),
]
