# gym_visits/urls.py

from django.urls import path
from gym_visits.views import (
    NfcCardCheckInAPIView,
    NfcCardCheckOutAPIView,
    ManualCheckInAPIView,
    ManualCheckOutAPIView,
)

app_name = "gym_visits"

urlpatterns = [
    path(
        "<uuid:gym_id>/visits/check-in/nfc/",
        NfcCardCheckInAPIView.as_view(),
        name="gym-visit-check-in",
    ),
    path(
        "<uuid:gym_id>/visits/check-out/nfc/",
        NfcCardCheckOutAPIView.as_view(),
        name="gym-visit-check-out",
    ),
    path(
        "<uuid:gym_id>/visits/check-in/manual/",
        ManualCheckInAPIView.as_view(),
        name="gym-visit-manual-check-in",
    ),
    path(
        "<uuid:gym_id>/visits/check-out/manual/",
        ManualCheckOutAPIView.as_view(),
        name="gym-visit-manual-check-out",
    ),
]
