# gym/urls.py

from django.urls import path
from .views import (
    GymListAPIView,
    GymDetailAPIView,
    GymCreateAPIView,
    GymUpdateAPIView,
    GymDeleteAPIView,
    GymPhotosAPIView,
    GymPhotoCreateAPIView,
    GymPhotoDeleteAPIView,
)

urlpatterns = [
    # Gym endpoints
    path(
        "",
        GymListAPIView.as_view(),
        name="gym-list",
    ),
    path(
        "<uuid:gym_id>/",
        GymDetailAPIView.as_view(),
        name="gym-detail",
    ),
    path(
        "create/",
        GymCreateAPIView.as_view(),
        name="gym-create",
    ),
    path(
        "<uuid:gym_id>/update/",
        GymUpdateAPIView.as_view(),
        name="gym-update",
    ),
    path(
        "<uuid:gym_id>/delete/",
        GymDeleteAPIView.as_view(),
        name="gym-delete",
    ),
    # Photo endpoints
    path(
        "<uuid:gym_id>/photos/",
        GymPhotosAPIView.as_view(),
        name="gym-photos",
    ),
    path(
        "<uuid:gym_id>/photos/create/",
        GymPhotoCreateAPIView.as_view(),
        name="gym-photo-create",
    ),
    path(
        "<uuid:gym_id>/photos/<uuid:photo_id>/delete/",
        GymPhotoDeleteAPIView.as_view(),
        name="gym-photo-delete",
    ),
]
