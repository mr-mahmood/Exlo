# gym_devices/views.py

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from gym_auth.permissions import IsAdmin
from gym.models import Gym
from core.pagination import CustomPagination
from .models import GymDevice
from .serializers import GymDeviceSerializer
from core.cache import GYM_DEVICES, cache_key, get_cache, invalidate_gym_device_caches


class GymDevicesAPIView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = GymDeviceSerializer
    pagination_class = CustomPagination

    def get(self, request, gym_id):
        key = cache_key(GYM_DEVICES, gym_id, request=request)

        def build():
            gym = Gym.objects.get_gym(gym_id=gym_id)
            devices = GymDevice.objects.filter(gym=gym).select_related("gym")
            paginator = self.pagination_class()
            result_page = paginator.paginate_queryset(devices, request, view=self)
            serializer = self.serializer_class(
                result_page,
                many=True,
                context={"request": request},
            )
            return paginator.get_paginated_data(serializer.data, "devices")

        data = get_cache(key, build)
        return Response(data, status=status.HTTP_200_OK)


class GymDevicesCreateAPIView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = GymDeviceSerializer

    def post(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id=gym_id)

        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        device_type = serializer.validated_data["device_type"]
        device, raw_token = GymDevice.objects.register_device(
            gym=gym,
            device_type=device_type,
        )

        invalidate_gym_device_caches(gym.id)

        return Response(
            {
                "device": self.serializer_class(
                    device, context={"request": request}
                ).data,
                "token": raw_token,
            },
            status=status.HTTP_201_CREATED,
        )


class GymDevicesDeActivateAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, gym_id, device_id):
        gym = Gym.objects.get_gym(gym_id)
        device = GymDevice.objects.get_device(device_id=device_id, gym=gym)
        device.deactivate_device()
        invalidate_gym_device_caches(gym.id)
        return Response(status=status.HTTP_200_OK)


class GymDevicesActivateAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, gym_id, device_id):
        gym = Gym.objects.get_gym(gym_id)
        device = GymDevice.objects.get_device(device_id=device_id, gym=gym)
        device.activate_device()
        invalidate_gym_device_caches(gym.id)
        return Response(status=status.HTTP_200_OK)
