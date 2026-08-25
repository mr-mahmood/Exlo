from rest_framework.permissions import BasePermission


class IsUserActive(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_user_active
        )


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_user_active
            and request.user.is_staff
            and request.user.is_superuser
        )


# class IsCoach(BasePermission):
#     def has_permission(self, request, view):
#         user = request.user

#         if not user or not user.is_authenticated:
#             return False

#         if not user.is_user_active:
#             return False

#         return CoachProfile.objects.filter(
#             user=user,
#             # status=CoachProfile.Status.ACTIVE,
#         ).exists()


# class IsGymOwner(BasePermission):
#     def has_permission(self, request, view):
#         user = request.user

#         if not user or not user.is_authenticated:
#             return False

#         if not user.is_user_active:
#             return False

#         return UserGymRole.objects.filter(
#             user=user,
#             role=UserGymRole.Role.OWNER,
#             deleted_at__isnull=True,
#         ).exists()
