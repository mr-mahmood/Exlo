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
from core.cache import (
    GYM_LIST,
    GYM_DETAIL,
    cache_key,
    get_cache,
    invalidate_gym_list_cache,
    invalidate_gym_caches,
)


class GymListAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GymSerializer
    pagination_class = CustomPagination

    def get(self, request):
        paginator = self.pagination_class()
        key = cache_key(GYM_LIST, request=request)

        def build():
            gyms = Gym.objects.filter(is_active=True).prefetch_related("photos")
            result_page = paginator.paginate_queryset(gyms, request, view=self)
            serializer = self.serializer_class(
                result_page,
                many=True,
                context={"request": request},
            )
            return paginator.get_paginated_data(serializer.data, "gyms")

        data = get_cache(key, build)
        return Response(data, status=status.HTTP_200_OK)


class GymDetailAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GymSerializer

    def get(self, request, gym_id):
        key = cache_key(GYM_DETAIL, gym_id)

        def build():
            gym = Gym.objects.get_gym(gym_id)
            serializer = self.serializer_class(gym, context={"request": request})
            return {"gym": serializer.data}

        data = get_cache(key, build)
        return Response(data, status=status.HTTP_200_OK)


class GymCreateAPIView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = GymSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        gym = serializer.save()

        invalidate_gym_list_cache()

        return Response(
            {"gym": self.serializer_class(gym, context={"request": request}).data},
            status=status.HTTP_201_CREATED,
        )


class GymUpdateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymSerializer

    def put(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id=gym_id, active_only=False)

        serializer = self.serializer_class(
            gym,
            data=request.data,
            context={"request": request},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        invalidate_gym_caches(gym.id)

        return Response({"gym": serializer.data}, status=status.HTTP_200_OK)


class GymDeleteAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]

    def delete(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id=gym_id, active_only=False)
        gym.deactivate()

        invalidate_gym_caches(gym.id)

        return Response(status=status.HTTP_200_OK)


class GymRestoreAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]

    def post(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id=gym_id, active_only=False)
        gym.activate()

        invalidate_gym_caches(gym.id)

        return Response(status=status.HTTP_200_OK)
