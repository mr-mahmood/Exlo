# gym_plans/urls.py

from django.urls import path
from .views import (
    GymPlansAPIView,
    GymPlansCreateAPIView,
    GymPlansUpdateAPIView,
    GymPlansDeleteAPIView,
)

app_name = "gym_plans"

urlpatterns = [
    path(
        "<uuid:gym_id>/plans/",
        GymPlansAPIView.as_view(),
        name="list",
    ),
    path(
        "<uuid:gym_id>/plans/create/",
        GymPlansCreateAPIView.as_view(),
        name="create",
    ),
    path(
        "<uuid:gym_id>/plans/<uuid:plan_id>/update/",
        GymPlansUpdateAPIView.as_view(),
        name="update",
    ),
    path(
        "<uuid:gym_id>/plans/<uuid:plan_id>/delete/",
        GymPlansDeleteAPIView.as_view(),
        name="delete",
    ),
]
