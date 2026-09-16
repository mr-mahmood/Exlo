# gym_visits/urls.py

from django.urls import path
from gym_visits.views import NfcCardCheckInView, NfcCardCheckOutView

app_name = "gym_visits"

urlpatterns = [
    path(
        "<uuid:gym_id>/visits/nfc/check-in/",
        NfcCardCheckInView.as_view(),
        name="gym-visit-check-in",
    ),
    path(
        "<uuid:gym_id>/visits/nfc/check-out/",
        NfcCardCheckOutView.as_view(),
        name="gym-visit-check-out",
    ),
]
