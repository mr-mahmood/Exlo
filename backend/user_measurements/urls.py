# user_measurements/urls.py

from django.urls import path
from .views import (
    UserMeasurementsListView,
    UserMeasurementDetailView,
    MeasurementPhotosView,
    MeasurementPhotoDetailView,
)

app_name = "user_measurements"

urlpatterns = [
    path(
        "",
        UserMeasurementsListView.as_view(),
        name="list",
    ),
    path(
        "<uuid:measurement_id>/",
        UserMeasurementDetailView.as_view(),
        name="detail",
    ),
    path(
        "<uuid:measurement_id>/photos/",
        MeasurementPhotosView.as_view(),
        name="photos-list",
    ),
    path(
        "<uuid:measurement_id>/photos/<uuid:photo_id>/",
        MeasurementPhotoDetailView.as_view(),
        name="photo-detail",
    ),
]
