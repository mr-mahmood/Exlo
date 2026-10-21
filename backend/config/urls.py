# config/urls.py

from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth apps
    path("api/auth/", include("authentication.urls")),
    # User apps
    path("api/users/", include("users.urls")),
    path("api/sessions/", include("users_sessions.urls")),
    path("api/referrals/", include("users_referrals.urls")),
    path("api/measurements/", include("users_measurements.urls")),
    # Gym apps
    path("api/gym/", include("gym.urls")),
    path("api/gym/", include("gym_auth.urls")),
    path("api/gym/", include("gym_photos.urls")),
    path("api/gym/", include("gym_announcements.urls")),
    path("api/gym/", include("gym_plans.urls")),
    path("api/gym/", include("gym_visits.urls")),
    path("api/gym/", include("gym_devices.urls")),
    path("api/gym/", include("gym_locks.urls")),
    path("api/gym/", include("users_nfc_cards.urls")),
    path("api/gym/subscriptions/", include("gym_subscriptions.urls")),
    # commerce apps
    path("api/commerce/wallet/", include("commerce_wallet.urls")),
    path("api/commerce/wallet-ledger/", include("commerce_wallet_ledger.urls")),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
