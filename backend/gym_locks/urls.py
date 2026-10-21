# gym_locks/urls.py

from django.urls import path

from .views import (
    LockerListAPIView,
    LockerCreateAPIView,
    LockerActivateAPIView,
    LockerDeActivateAPIView,
    NfcCardLockerOpenAPIView,
    ManualLockerOpenAPIView,
)

app_name = "gym_locks"

urlpatterns = [
    path(
        "<uuid:gym_id>/create/",
        LockerCreateAPIView.as_view(),
        name="gym_locks-create",
    ),
    path(
        "<uuid:gym_id>/lockers/",
        LockerListAPIView.as_view(),
        name="gym_locks-list",
    ),
    path(
        "<uuid:gym_id>/lockers/<uuid:locker_id>/activate",
        LockerActivateAPIView.as_view(),
        name="gym_locks-activate",
    ),
    path(
        "<uuid:gym_id>/lockers/<uuid:locker_id>/deactivate",
        LockerDeActivateAPIView.as_view(),
        name="gym_locks-deactivate",
    ),
    path(
        "<uuid:gym_id>/lockers/open/nfc/",
        NfcCardLockerOpenAPIView.as_view(),
        name="gym_locks-open-nfc",
    ),
    path(
        "<uuid:gym_id>/lockers/open/manual/",
        ManualLockerOpenAPIView.as_view(),
        name="gym_locks-open-manual",
    ),
]
