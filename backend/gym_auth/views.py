# gym_auth/views.py

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from authentication.permissions import IsAdmin
from core.pagination import CustomPagination
from .permissions import IsAdminOrGymOwner
from users.models import User
from gym.models import Gym
from .models import UserGymRole
from .serializers import UserGymRoleSerializer
from core.errors import APIError, UserGymRoleError


class GymUserRoleListAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = UserGymRoleSerializer
    pagination_class = CustomPagination

    def get(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id)
        roles = gym.users.select_related("user").all()  # type: ignore

        paginator = self.pagination_class()
        result_page = paginator.paginate_queryset(roles, request, view=self)

        serializer = self.serializer_class(
            result_page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data, "users")


class GymOwnerCreateAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, gym_id):
        user_id = request.data.get("user")
        user = User.objects.get_user(user_id)
        gym = Gym.objects.get_gym(gym_id)
        UserGymRole.objects.create_owner(user, gym)
        return Response(status=status.HTTP_200_OK)


class GymCoachCreateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]

    def post(self, request, gym_id):
        user_id = request.data.get("user")
        user = User.objects.get_user(user_id)
        gym = Gym.objects.get_gym(gym_id)
        UserGymRole.objects.create_coach(user, gym)
        return Response(status=status.HTTP_200_OK)


class GymStaffCreateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]

    def post(self, request, gym_id):
        user_id = request.data.get("user")
        user = User.objects.get_user(user_id)
        gym = Gym.objects.get_gym(gym_id)
        UserGymRole.objects.create_staff(user, gym)
        return Response(status=status.HTTP_200_OK)


class GymRoleDeleteAPIView(APIView):
    permission_classes = [IsAdmin]

    def delete(self, request, gym_id, role_id):
        role = UserGymRole.objects.filter(
            id=role_id,
            gym_id=gym_id,
        ).first()

        if role is None:
            raise APIError(UserGymRoleError.ROLE_NOT_FOUND)

        role.delete()
        return Response(status=status.HTTP_200_OK)


class GymStaffRoleDeleteAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]

    def delete(self, request, gym_id, role_id):
        role = UserGymRole.objects.filter(
            id=role_id,
            gym_id=gym_id,
            role__in=[UserGymRole.Role.COACH, UserGymRole.Role.STAFF],
        ).first()

        if role is None:
            raise APIError(UserGymRoleError.ROLE_NOT_FOUND)

        role.delete()
        return Response(status=status.HTTP_200_OK)
