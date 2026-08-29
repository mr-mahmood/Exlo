# user_measurements/urls.py

from django.urls import path
from .views import UserMeasurementsListView, UserMeasurementDetailView

app_name = "user_measurements"

urlpatterns = [
    path("", UserMeasurementsListView.as_view(), name="list"),
    path("<uuid:pk>/", UserMeasurementDetailView.as_view(), name="detail"),
]
