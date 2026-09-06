# gym_announcements/urls.py

from django.urls import path
from .views import (
    GymAnnouncementAPIView,
    GymAnnouncementCreateAPIView,
    GymAnnouncementUpdateAPIView,
    GymAnnouncementDeleteAPIView,
)

app_name = "gym_announcements"

urlpatterns = [
    path(
        "<uuid:gym_id>/announcements/",
        GymAnnouncementAPIView.as_view(),
        name="list",
    ),
    path(
        "<uuid:gym_id>/announcements/create/",
        GymAnnouncementCreateAPIView.as_view(),
        name="create",
    ),
    path(
        "<uuid:gym_id>/announcements/<uuid:announcement_id>/update/",
        GymAnnouncementUpdateAPIView.as_view(),
        name="update",
    ),
    path(
        "<uuid:gym_id>/announcements/<uuid:announcement_id>/delete/",
        GymAnnouncementDeleteAPIView.as_view(),
        name="delete",
    ),
]
