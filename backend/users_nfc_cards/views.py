from django.core.cache import cache
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

from users_nfc_cards.permissions import CanAssignUserNfcCard
from users.models import User
from users.utils import normalize_phone
from gym_subscriptions.models import GymSubscription
from core.errors import APIError, UserNfcCardError, GymSubscriptionError


class UserNfcCardAssignRequestView(APIView):
    permission_classes = [CanAssignUserNfcCard]

    def post(self, request, gym_id):
        phone_number = normalize_phone(request.data.get("phone_number"))
        user = User.objects.get_user_by_phone(phone_number)
        user.validate_account_status()

        if not GymSubscription.objects.filter(
            Q(status=GymSubscription.Status.PENDING)
            | Q(status=GymSubscription.Status.ACTIVE, expires_at__gt=timezone.now()),
            subscriber=user,
            gym_id=gym_id,
            remaining_visits__gt=0,
        ).exists():
            raise APIError(GymSubscriptionError.NO_ACTIVE_SUBSCRIPTION)

        created = cache.add(
            f"nfc_card_assign_{gym_id}",
            user.pk,
            timeout=5 * 60,
        )

        if not created:
            raise APIError(UserNfcCardError.CARD_ASSIGNMENT_ALREADY_PENDING)

        return Response(status=status.HTTP_201_CREATED)
