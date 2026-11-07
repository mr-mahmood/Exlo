# gym_auth/urls.py

from django.urls import path

from .views import (
    GymUserRoleListAPIView,
    GymOwnerCreateAPIView,
    GymCoachCreateAPIView,
    GymStaffCreateAPIView,
    GymRoleDeleteAPIView,
)

app_name = "gym_auth"

urlpatterns = [
    path(
        "<uuid:gym_id>/roles/",
        GymUserRoleListAPIView.as_view(),
        name="gym-roles-list",
    ),
    path(
        "<uuid:gym_id>/owner/create/",
        GymOwnerCreateAPIView.as_view(),
        name="gym-owner-create",
    ),
    path(
        "<uuid:gym_id>/coach/create/",
        GymCoachCreateAPIView.as_view(),
        name="gym-coach-create",
    ),
    path(
        "<uuid:gym_id>/staff/create/",
        GymStaffCreateAPIView.as_view(),
        name="gym-staff-create",
    ),
    path(
        "<uuid:gym_id>/roles/<uuid:role_id>/delete/",
        GymRoleDeleteAPIView.as_view(),
        name="gym-role-delete",
    ),
]
