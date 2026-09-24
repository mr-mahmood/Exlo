from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from users_nfc_cards.permissions import CanAssignUserNfcCard
from users.models import User
from core.errors import APIError, UserNfcCardError
from users.validators import validate_phone


class UserNfcCardAssignRequestView(APIView):
    permission_classes = [CanAssignUserNfcCard]

    def post(self, request, gym_id):
        phone = validate_phone(
            value=request.data.get("phone"),
            skip_duplicate_check=True,
        )

        user = User.objects.get_user_by_phone(phone_number=phone)

        self.check_object_permissions(request, user)

        created = cache.add(
            f"nfc_card_assign_{gym_id}",
            user.pk,
            timeout=5 * 60,
        )

        if not created:
            raise APIError(UserNfcCardError.CARD_ASSIGNMENT_ALREADY_PENDING)

        return Response(status=status.HTTP_201_CREATED)
