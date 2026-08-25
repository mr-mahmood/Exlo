# user_referrals/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from core.errors import ReferralError, APIError
from users.models import User
from .serializers import UserReferralSerializer
from .models import Referral


class UserReferralPIView(APIView):
    serializer_class = UserReferralSerializer

    def get(self, request):
        """Get all referrals made by the user with nested user details"""

        user: User = request.user

        # prevent n+1 query problem
        referrals = Referral.objects.filter(referrer=user).select_related(
            "referred_user"
        )

        if not referrals.exists():
            raise APIError(ReferralError.NO_EXISTING_REFERRAL)

        serializer = self.serializer_class(
            referrals,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "referrals": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
