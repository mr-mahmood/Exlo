from rest_framework.permissions import BasePermission

from authentication.permissions import IsAdmin
from gym_auth.permissions import IsGymOwner, IsGymStaff
from gym_subscriptions.permissions import IsGymMember


class CanViewGymAnnouncements(BasePermission):
    def has_permission(self, request, view):
        return any(
            permission().has_permission(request, view)
            for permission in (IsAdmin, IsGymOwner, IsGymStaff, IsGymMember)
        )
