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
from gym_locks.models import GymLocker


class NfcCardCheckInView(APIView):
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


class NfcCardCheckOutView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsGymGate]

    def post(self, request, gym_id):
        device = request.auth
        gym = device.gym

        uid = request.data.get("uid")
        user: User = UserNfcCard.objects.find_card(uid=uid).user
        user.validate_account_status()

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
