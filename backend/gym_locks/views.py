# gym_locks/views.py

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from core.pagination import LockerPagination
from gym.models import Gym
from .models import GymLocker
from .serializers import GymLockerSerializer
from gym_auth.permissions import IsAdminOrGymOwnerOrGymStaff
from authentication.permissions import IsAdmin
from gym_devices.authentication import DeviceTokenAuthentication
from gym_devices.permissions import IsGymLocker
from users_nfc_cards.models import UserNfcCard
from users.models import User
from users.validators import validate_phone
from core.cache import GYM_LOCKERS, cache_key, get_cache, invalidate_gym_locker_caches


class LockerListAPIView(APIView):
    permission_classes = [IsAdminOrGymOwnerOrGymStaff]
    pagination_class = LockerPagination
    serializer_class = GymLockerSerializer

    def get(self, request, gym_id):
        key = cache_key(GYM_LOCKERS, gym_id, request=request)

        def build():
            gym = Gym.objects.get_gym(gym_id)
            lockers = GymLocker.objects.get_gym_lockers(gym)
            paginator = self.pagination_class()
            result_page = paginator.paginate_queryset(lockers, request, view=self)
            serializer = self.serializer_class(
                result_page,
                many=True,
                context={"request": request},
            )
            return paginator.get_paginated_data(serializer.data, "lockers")

        data = get_cache(key, build)
        return Response(data, status=status.HTTP_200_OK)


class LockerCreateAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, gym_id):
        count = request.data.get("count")
        gym = Gym.objects.get_gym(gym_id)
        lockers = GymLocker.objects.add_lockers(gym=gym, count=count)
        invalidate_gym_locker_caches(gym.id)
        return Response(status=status.HTTP_201_CREATED)


class LockerActivateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwnerOrGymStaff]

    def post(self, request, gym_id, locker_id):
        gym = Gym.objects.get_gym(gym_id)
        locker: GymLocker = GymLocker.objects.get_lock(gym, locker_id)
        locker.activate()
        invalidate_gym_locker_caches(gym.id)
        return Response(status=status.HTTP_200_OK)


class LockerDeActivateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwnerOrGymStaff]

    def post(self, request, gym_id, locker_id):
        gym = Gym.objects.get_gym(gym_id)
        locker: GymLocker = GymLocker.objects.get_lock(gym, locker_id)
        locker.deactivate()
        invalidate_gym_locker_caches(gym.id)
        return Response(status=status.HTTP_200_OK)


class NfcCardLockerOpenAPIView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsGymLocker]

    # look open dont need user to be active
    def post(self, request, gym_id):
        device = request.auth
        gym = device.gym
        uid = request.data.get("uid")
        card = UserNfcCard.objects.find_card(uid=uid)
        locker = GymLocker.objects.get_user_locker(gym=gym, user=card.user)
        return Response({"locker_number": locker.number}, status=status.HTTP_200_OK)


class ManualLockerOpenAPIView(APIView):
    permission_classes = [IsAdminOrGymOwnerOrGymStaff]

    def post(self, request, gym_id):
        phone_number = validate_phone(
            request.data.get("phone_number"), skip_duplicate_check=True
        )
        # look open dont need user to be active
        user = User.objects.get_user_by_phone(phone_number)
        gym = Gym.objects.get_gym(gym_id)
        locker = GymLocker.objects.get_user_locker(gym=gym, user=user)

        # TODO: send websocket order to the gym esp32 device to open this lcok
        # TODO: Handle device offline / command failure.

        return Response({"locker_number": locker.number}, status=status.HTTP_200_OK)
