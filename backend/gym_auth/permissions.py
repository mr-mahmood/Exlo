# gym_auth/permissions.py

from rest_framework.permissions import BasePermission
from authentication.permissions import IsAdmin, IsUserActive
from gym_auth.models import UserGymRole


class IsGymOwner(BasePermission):
    def has_permission(self, request, view):
        user = request.user

        # Must have gym_id in URL
        gym_id = view.kwargs.get("gym_id")
        if not gym_id:
            return False

        # User must be active and authenticated
        if not IsUserActive().has_permission(request, view):
            return False

        # Check if user is owner of this gym
        return UserGymRole.objects.filter(
            user=user,
            gym_id=gym_id,
            role=UserGymRole.Role.OWNER,
        ).exists()


class IsGymStaff(BasePermission):
    def has_permission(self, request, view):
        user = request.user

        # Must have gym_id in URL
        gym_id = view.kwargs.get("gym_id")
        if not gym_id:
            return False

        # User must be active and authenticated
        if not IsUserActive().has_permission(request, view):
            return False

        # Check if user is staff of this gym
        return UserGymRole.objects.filter(
            user=user,
            gym_id=gym_id,
            role__in=[UserGymRole.Role.OWNER, UserGymRole.Role.STAFF],
        ).exists()


class IsGymCoach(BasePermission):
    """Check if user is a coach at the gym"""
    def has_permission(self, request, view):
        user = request.user

        # Must have gym_id in URL
        gym_id = view.kwargs.get("gym_id")
        if not gym_id:
            return False

        # User must be active and authenticated
        if not IsUserActive().has_permission(request, view):
            return False

        # Check if user is coach of this gym
        return UserGymRole.objects.filter(
            user=user,
            gym_id=gym_id,
            role=UserGymRole.Role.COACH,
        ).exists()


class IsGymAthlete(BasePermission):
    def has_permission(self, request, view):
        user = request.user

        # Must have gym_id in URL
        gym_id = view.kwargs.get("gym_id")
        if not gym_id:
            return False

        # User must be active and authenticated
        if not IsUserActive().has_permission(request, view):
            return False

        # Check if user is athlete of this gym
        return UserGymRole.objects.filter(
            user=user,
            gym_id=gym_id,
            role=UserGymRole.Role.ATHLETE,
        ).exists()


class IsGymMember(BasePermission):
    def has_permission(self, request, view):
        user = request.user

        # Must have gym_id in URL
        gym_id = view.kwargs.get("gym_id")
        if not gym_id:
            return False

        # User must be active and authenticated
        if not IsUserActive().has_permission(request, view):
            return False

        # Check if user has ANY role in this gym
        return UserGymRole.objects.filter(
            user=user,
            gym_id=gym_id,
        ).exists()


class IsAdminOrGymOwner(BasePermission):
    def has_permission(self, request, view):
        return bool(
            IsAdmin().has_permission(request, view)
            or IsGymOwner().has_permission(request, view)
        )


class IsAdminOrGymStaff(BasePermission):
    def has_permission(self, request, view):
        return bool(
            IsAdmin().has_permission(request, view)
            or IsGymStaff().has_permission(request, view)
        )