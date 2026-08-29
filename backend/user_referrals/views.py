# user_referrals/views.py
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from core.errors import ReferralError, APIError
from users.models import User
from .serializers import UserReferralSerializer
from .models import Referral
from core.pagination import CustomPagination


class UserReferralPIView(APIView):
    serializer_class = UserReferralSerializer
    pagination_class = CustomPagination

    def get(self, request):
        """Get all referrals made by the user with nested user details"""

        user: User = request.user

        # prevent n+1 query problem
        referrals = Referral.objects.filter(referrer=user).select_related(
            "referred_user"
        )

        #  Referral.DoesNotExist only work for get not filter
        if not referrals.exists():
            raise APIError(ReferralError.NO_EXISTING_REFERRAL)

        paginator = self.pagination_class()
        result_page = paginator.paginate_queryset(referrals, request, view=self)

        serializer = self.serializer_class(
            result_page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data, "referrals")
