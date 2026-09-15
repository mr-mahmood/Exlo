# users_nfc_cards/urls.py

from django.urls import path
from users_nfc_cards.views import UserNfcCardAssignView

app_name = "users_nfc_cards"

urlpatterns = [
    path(
        "<uuid:user_id>/nfc-card/assign",
        UserNfcCardAssignView.as_view(),
        name="assign",
    ),
]
