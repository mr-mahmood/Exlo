# gym_visits/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from gym_subscriptions.models import GymSubscription
from core.errors import APIError, GymSubscriptionError, GymVisitsError
from gym_visits.models import GymVisit
from gym_devices.authentication import DeviceTokenAuthentication
from gym_devices.permissions import IsGymGate
from users_nfc_cards.models import UserNfcCard
from users.models import User
from users.utils import normalize_phone
from gym.models import Gym
from gym_locks.models import GymLocker
from gym_auth.permissions import IsAdminOrGymOwnerOrGymStaff
from gym_visits.permissions import CanManageManualCheckInAndOut


class NfcCardCheckInAPIView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsGymGate]

    def post(self, request, gym_id):
        device = request.auth
        gym = device.gym

        uid = request.data.get("uid")

        card, card_assigned = UserNfcCard.objects.find_or_assign_card(
            uid=uid,
            gym_id=gym_id,
        )

        if card_assigned:
            # esp32 dont open gate just assign card to user
            return Response(status=status.HTTP_201_CREATED)

        user: User = card.user
        user.validate_account_status()

        subscription_error = None
        with transaction.atomic():

            User.objects.select_for_update().get(pk=user.pk)
            if GymVisit.objects.filter(user=user, checked_out_at__isnull=True).exists():
                raise APIError(GymVisitsError.ALREADY_CHECKED_IN)

            try:
                subscription = GymSubscription.objects.consume_visit(
                    subscriber=user,
                    gym=gym,
                )
            except APIError as exc:
                if exc.error_code != GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0]:
                    raise
                subscription_error = exc
            else:
                GymVisit.objects.check_in(
                    user=user,
                    gym=gym,
                    subscription=subscription,
                    method=GymVisit.Method.NFC,
                )

                GymLocker.objects.assign(gym, user)

        if subscription_error is not None:
            raise subscription_error

        # esp32 open gate
        return Response(status=status.HTTP_200_OK)


class NfcCardCheckOutAPIView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsGymGate]

    def post(self, request, gym_id):
        device = request.auth
        gym = device.gym

        uid = request.data.get("uid")
        # check out dont need user to be active
        user: User = UserNfcCard.objects.find_card(uid=uid).user

        with transaction.atomic():
            User.objects.select_for_update().get(pk=user.pk)
            visit: GymVisit = GymVisit.objects.filter(
                user=user,
                gym=gym,
                checked_out_at__isnull=True,
            ).first()

            if visit is None:
                raise APIError(GymVisitsError.VISIT_NOT_FOUND)

            GymLocker.objects.remove_assignment(gym, user)
            visit.check_out(method=GymVisit.Method.NFC)

        return Response(status=status.HTTP_200_OK)


class ManualCheckInAPIView(APIView):
    permission_classes = [CanManageManualCheckInAndOut]

    def post(self, request, gym_id):
        phone_number = normalize_phone(request.data.get("phone_number"))
        user = User.objects.get_user_by_phone(phone_number)
        user.validate_account_status()
        gym = Gym.objects.get_gym(gym_id)

        subscription_error = None
        with transaction.atomic():

            User.objects.select_for_update().get(pk=user.pk)
            if GymVisit.objects.filter(user=user, checked_out_at__isnull=True).exists():
                raise APIError(GymVisitsError.ALREADY_CHECKED_IN)

            try:
                subscription = GymSubscription.objects.consume_visit(
                    subscriber=user,
                    gym=gym,
                )
            except APIError as exc:
                if exc.error_code != GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION[0]:
                    raise
                subscription_error = exc
            else:
                GymVisit.objects.check_in(
                    user=user,
                    gym=gym,
                    subscription=subscription,
                    method=GymVisit.Method.STAFF,
                )

                GymLocker.objects.assign(gym, user)

        if subscription_error is not None:
            raise subscription_error

        # esp32 open gate
        return Response(status=status.HTTP_200_OK)


class ManualCheckOutAPIView(APIView):
    permission_classes = [CanManageManualCheckInAndOut]

    def post(self, request, gym_id):
        phone_number = normalize_phone(request.data.get("phone_number"))
        # check out dont need user to be active
        user = User.objects.get_user_by_phone(phone_number)
        gym = Gym.objects.get_gym(gym_id)

        with transaction.atomic():
            User.objects.select_for_update().get(pk=user.pk)
            visit: GymVisit = GymVisit.objects.filter(
                user=user,
                gym=gym,
                checked_out_at__isnull=True,
            ).first()

            if visit is None:
                raise APIError(GymVisitsError.VISIT_NOT_FOUND)

            GymLocker.objects.remove_assignment(gym, user)
            visit.check_out(method=GymVisit.Method.STAFF)

        # TODO: send websocket order to the gym esp32 device to open this lcok
        # TODO: Handle device offline / command failure.

        return Response(status=status.HTTP_200_OK)
