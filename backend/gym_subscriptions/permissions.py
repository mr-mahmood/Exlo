from django.utils import timezone
from rest_framework.permissions import BasePermission

from authentication.permissions import IsUserActive
from .models import GymSubscription


class IsGymMember(BasePermission):
    def has_permission(self, request, view):
        gym_id = view.kwargs.get("gym_id")
        if not gym_id or not IsUserActive().has_permission(request, view):
            return False

        return GymSubscription.objects.filter(
            subscriber=request.user,
            plan__gym_id=gym_id,
            status=GymSubscription.Status.ACTIVE,
            expires_at__gt=timezone.now(),
            remaining_visits__gt=0,
        ).exists()
