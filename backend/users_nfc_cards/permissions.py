from rest_framework.permissions import BasePermission
from authentication.permissions import IsAdmin, IsUserActive
from gym_auth.models import UserGymRole
from gym_subscriptions.models import GymSubscription


class CanAssignUserNfcCard(BasePermission):

    def has_permission(self, request, view):
        return IsUserActive().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        gym_id = view.kwargs["gym_id"]

        if IsAdmin().has_permission(request, view):
            return (
                GymSubscription.objects.truly_active()
                .filter(
                    subscriber=obj,
                    plan__gym_id=gym_id,
                )
                .exists()
            )

        has_gym_access = UserGymRole.objects.filter(
            user=request.user,
            gym_id=gym_id,
            role__in=[
                UserGymRole.Role.OWNER,
                UserGymRole.Role.STAFF,
            ],
        ).exists()

        if not has_gym_access:
            return False

        return (
            GymSubscription.objects.truly_active()
            .filter(
                subscriber=obj,
                plan__gym_id=gym_id,
            )
            .exists()
        )
