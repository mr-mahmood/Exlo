# gym_visits/urls.py

from django.urls import path
from gym_visits.views import CheckInView, CheckOutView

app_name = "gym_visits"

urlpatterns = [
    path(
        "<uuid:gym_id>/visits/device/check-in/",
        CheckInView.as_view(),
        name="gym-visit-check-in",
    ),
    path(
        "<uuid:gym_id>/visits/device/check-out/",
        CheckOutView.as_view(),
        name="gym-visit-check-out",
    ),
]
