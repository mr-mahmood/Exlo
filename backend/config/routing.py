# config/routing.py

from django.urls import path
from gym_devices.middleware import DeviceAuthMiddleware
from gym_visits.consumers import GateConsumer
from gym_locks.consumers import LockerConsumer

websocket_urlpatterns = [
    path(
        "ws/<uuid:gym_id>/gate/",
        DeviceAuthMiddleware(GateConsumer.as_asgi()),
    ),
    path(
        "ws/<uuid:gym_id>/lockers/",
        DeviceAuthMiddleware(LockerConsumer.as_asgi()),
    ),
]
