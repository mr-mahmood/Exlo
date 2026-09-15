# users_nfc_cards/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from users_nfc_cards.permissions import CanAssignUserNfcCard
from users.models import User
from users_nfc_cards.models import UserNfcCard
from core.errors import APIError, UserNfcCardError


class UserNfcCardAssignView(APIView):
    permission_classes = [CanAssignUserNfcCard]

    def post(self, request, user_id):
        user = User.objects.get_user(user_id)

        self.check_object_permissions(request, user)

        uid = request.data.get("uid", "")
        if not isinstance(uid, str):
            raise APIError(UserNfcCardError.INVALID_UID)

        card = UserNfcCard.objects.assign_card(
            user=user,
            uid=uid,
            assigned_by=request.user,
        )

        return Response(status=status.HTTP_201_CREATED)
