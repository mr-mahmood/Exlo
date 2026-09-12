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
    path("api/gym/", include("gym_photos.urls")),
    path("api/gym/", include("gym_announcements.urls")),
    path("api/gym/", include("gym_plans.urls")),
    path("api/subscriptions/", include("gym_subscriptions.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
