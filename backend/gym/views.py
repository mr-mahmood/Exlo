# gym/views.py

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from authentication.permissions import IsAdmin
from gym_auth.permissions import IsAdminOrGymOwner
from gym.models import Gym
from gym.serializers import GymSerializer
from core.pagination import CustomPagination
from core.errors import APIError, GymError
from typing import cast


class GymListAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GymSerializer
    pagination_class = CustomPagination

    def get(self, request):
        gyms = Gym.objects.filter(is_active=True).prefetch_related("photos")

        paginator = self.pagination_class()
        result_page = paginator.paginate_queryset(gyms, request, view=self)

        serializer = self.serializer_class(
            result_page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data, "gyms")


class GymDetailAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GymSerializer

    def get(self, request, gym_id):
        try:
            gym = (
                Gym.objects.filter(id=gym_id, is_active=True)
                .prefetch_related("photos")
                .first()
            )

            if not gym:
                raise APIError(GymError.GYM_NOT_FOUND)

        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        serializer = self.serializer_class(
            gym,
            context={"request": request},
        )

        return Response({"gym": serializer.data}, status=status.HTTP_200_OK)


class GymCreateAPIView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = GymSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        gym = cast(Gym, serializer.save())

        return Response(
            {
                "gym": self.serializer_class(
                    gym,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class GymUpdateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymSerializer

    def put(self, request, gym_id):
        try:
            gym = Gym.objects.get(id=gym_id)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        serializer = self.serializer_class(
            gym,
            data=request.data,
            context={"request": request},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "gym": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class GymDeleteAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]

    def delete(self, request, gym_id):
        try:
            gym = Gym.objects.get(id=gym_id)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        # Check if gym has any active memberships
        if gym.has_active_memberships():
            raise APIError(GymError.GYM_HAS_ACTIVE_MEMBERSHIPS)

        gym.delete()

        return Response(status=status.HTTP_200_OK)
