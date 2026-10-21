# gym_devices/urls.py

from django.urls import path
from .views import (
    GymDevicesAPIView,
    GymDevicesCreateAPIView,
    GymDevicesDeActivateAPIView,
    GymDevicesActivateAPIView,
)

app_name = "gym_devices"

urlpatterns = [
    path(
        "<uuid:gym_id>/devices/",
        GymDevicesAPIView.as_view(),
        name="list",
    ),
    path(
        "<uuid:gym_id>/devices/create/",
        GymDevicesCreateAPIView.as_view(),
        name="create",
    ),
    path(
        "<uuid:gym_id>/devices/<uuid:device_id>/deactivate",
        GymDevicesDeActivateAPIView.as_view(),
        name="deactivate",
    ),
    path(
        "<uuid:gym_id>/devices/<uuid:device_id>/activate",
        GymDevicesActivateAPIView.as_view(),
        name="activate",
    ),
]
