# gym_visits/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from gym.models import Gym
from gym_subscriptions.models import GymSubscription
from core.errors import APIError, GymVisitsError
from gym_visits.models import GymVisit
from gym_devices.authentication import DeviceTokenAuthentication
from gym_devices.permissions import IsGymDevice
from users_nfc_cards.models import UserNfcCard
from users.models import User


class NfcCardCheckInView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsGymDevice]

    def post(self, request, gym_id):
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

        gym = Gym.objects.get_gym(gym_id)

        with transaction.atomic():
            subscription = GymSubscription.objects.consume_visit(
                subscriber=user,
                gym=gym,
            )

            GymVisit.objects.check_in(
                user=user,
                gym=gym,
                subscription=subscription,
                method=GymVisit.Method.NFC,
            )

        # esp32 open gate
        return Response(status=status.HTTP_200_OK)


class NfcCardCheckOutView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsGymDevice]

    def post(self, request, gym_id):

        uid = request.data.get("uid")
        user: User = UserNfcCard.objects.find_card(uid=uid).user
        user.validate_account_status()

        gym = Gym.objects.get_gym(gym_id)

        visit: GymVisit = GymVisit.objects.filter(
            user=user,
            gym=gym,
            checked_out_at__isnull=True,
        ).first()  # type: ignore

        if visit is None:
            raise APIError(GymVisitsError.VISIT_NOT_FOUND)

        visit.check_out(method=GymVisit.Method.NFC)

        return Response(status=status.HTTP_200_OK)
