from rest_framework.permissions import BasePermission
from authentication.permissions import IsAdmin, IsUserActive
from gym_auth.models import UserGymRole


class CanAssignUserNfcCard(BasePermission):

    def has_permission(self, request, view):
        if not IsUserActive().has_permission(request, view):
            return False

        if IsAdmin().has_permission(request, view):
            return True

        gym_id = view.kwargs["gym_id"]

        return UserGymRole.objects.filter(
            user=request.user,
            gym_id=gym_id,
            role__in=[
                UserGymRole.Role.OWNER,
                UserGymRole.Role.STAFF,
            ],
        ).exists()
