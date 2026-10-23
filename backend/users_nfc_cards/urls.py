# users_nfc_cards/urls.py

from django.urls import path
from users_nfc_cards.views import UserNfcCardAssignRequestView

app_name = "users_nfc_cards"

urlpatterns = [
    path(
        "<uuid:gym_id>/nfc-card/assign/",
        UserNfcCardAssignRequestView.as_view(),
        name="assign",
    ),
]
