# gym_visits/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from gym.models import Gym
from gym_subscriptions.models import GymSubscription
from core.errors import APIError, GymVisitsError
from gym_visits.models import GymVisit
from gym_visits.serializers import CheckInSerializer, CheckOutSerializer


class CheckInView(APIView):
    serializer_class = CheckInSerializer

    def post(self, request, gym_id):
        serializer = CheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        gym = Gym.objects.get_gym(gym_id)
        method = serializer.validated_data["method"]  # type: ignore

        with transaction.atomic():
            subscription = GymSubscription.objects.consume_visit(
                request.user,
                gym,
            )
            visit = GymVisit.objects.check_in(
                user=request.user,
                gym=gym,
                subscription=subscription,
                method=method,
            )

        return Response(status=status.HTTP_201_CREATED)


class CheckOutView(APIView):
    serializer_class = CheckOutSerializer

    def post(self, request, gym_id):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        gym = Gym.objects.get_gym(gym_id)
        method = serializer.validated_data["method"]  # type: ignore

        visit: GymVisit = GymVisit.objects.filter(
            user=request.user,
            gym=gym,
            checked_out_at__isnull=True,
        ).first()  # type: ignore

        if visit is None:
            raise APIError(GymVisitsError.VISIT_NOT_FOUND)

        visit.check_out(method=method)

        return Response(status=status.HTTP_200_OK)
