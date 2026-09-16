from rest_framework.permissions import BasePermission
from users.models import User


class IsUserActive(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
        )


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.is_staff
            and request.user.is_superuser
            and request.user.role == User.Role.ADMIN
        )
