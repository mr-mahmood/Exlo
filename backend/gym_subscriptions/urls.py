# gym_subscriptions/urls.py

from django.urls import path

from .views import (
    CancelSubscriptionAPIView,
    MySubscriptionDetailAPIView,
    MySubscriptionListAPIView,
)

app_name = "gym_subscriptions"

urlpatterns = [
    path(
        "",
        MySubscriptionListAPIView.as_view(),
        name="gym-subscription-list",
    ),
    path(
        "<uuid:subscription_id>/",
        MySubscriptionDetailAPIView.as_view(),
        name="gym-subscription-detail",
    ),
    path(
        "<uuid:subscription_id>/cancel/",
        CancelSubscriptionAPIView.as_view(),
        name="gym-subscription-cancel",
    ),
]
