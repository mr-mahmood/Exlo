# user_measurements/urls.py

from django.urls import path
from .views import (
    UserMeasurementsListAPIView,
    UserMeasurementCreateAPIView,
    UserMeasurementDetailAPIView,
    UserMeasurementUpdateAPIView,
    UserMeasurementDeleteAPIView,
    MeasurementPhotoListAPIView,
    MeasurementPhotoCreateAPIView,
    MeasurementPhotoDetailAPIView,
    MeasurementPhotoDeleteAPIView,
)

app_name = "user_measurements"

urlpatterns = [
    path(
        "",
        UserMeasurementsListAPIView.as_view(),
        name="list",
    ),
    path(
        "create/",
        UserMeasurementCreateAPIView.as_view(),
        name="create",
    ),
    path(
        "<uuid:measurement_id>/",
        UserMeasurementDetailAPIView.as_view(),
        name="detail",
    ),
    path(
        "<uuid:measurement_id>/update/",
        UserMeasurementUpdateAPIView.as_view(),
        name="update",
    ),
    path(
        "<uuid:measurement_id>/delete/",
        UserMeasurementDeleteAPIView.as_view(),
        name="delete",
    ),
    path(
        "<uuid:measurement_id>/photos/",
        MeasurementPhotoListAPIView.as_view(),
        name="photos-list",
    ),
    path(
        "<uuid:measurement_id>/photos/create/",
        MeasurementPhotoCreateAPIView.as_view(),
        name="photo-create",
    ),
    path(
        "<uuid:measurement_id>/photos/<uuid:photo_id>/",
        MeasurementPhotoDetailAPIView.as_view(),
        name="photo-detail",
    ),
    path(
        "<uuid:measurement_id>/photos/<uuid:photo_id>/delete/",
        MeasurementPhotoDeleteAPIView.as_view(),
        name="photo-delete",
    ),
]
