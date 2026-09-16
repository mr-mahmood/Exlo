# users_nfc_cards/permissions.py

from rest_framework.permissions import BasePermission
from authentication.permissions import IsAdmin, IsUserActive
from gym_auth.models import UserGymRole
from gym_subscriptions.models import GymSubscription


class CanAssignUserNfcCard(BasePermission):

    def has_permission(self, request, view):
        # Gate: caller must be an active user
        if not IsUserActive().has_permission(request, view):
            return False
        return True

    def has_object_permission(self, request, view, obj):

        # Admins can assign to any user.
        if IsAdmin().has_permission(request, view):
            return True

        # Gyms where the caller is OWNER or STAFF.
        caller_gym_ids = list(
            UserGymRole.objects.filter(
                user=request.user,
                role__in=[UserGymRole.Role.OWNER, UserGymRole.Role.STAFF],
            ).values_list("gym_id", flat=True)
        )

        if not caller_gym_ids:
            return False

        # Target must have a currently-active subscription at one of those gyms.
        return (
            GymSubscription.objects.truly_active()
            .filter(
                subscriber=obj,
                plan__gym_id__in=caller_gym_ids,
            )
            .exists()
        )
