# gym_subscriptions/views.py

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from core.pagination import CustomPagination
from .models import GymSubscription
from .serializers import GymSubscriptionReadSerializer


class MySubscriptionListAPIView(APIView):
    pagination_class = CustomPagination
    serializer_class = GymSubscriptionReadSerializer

    def get(self, request):

        subscriptions = GymSubscription.objects.select_related(
            "plan",
            "plan__gym",
        ).filter(
            subscriber=request.user,
        )

        status_param = request.query_params.get("status")
        if status_param:
            value = status_param.upper()
            if value in GymSubscription.Status.values:
                subscriptions = subscriptions.filter(status=value)

        paginator = self.pagination_class()
        result_page = paginator.paginate_queryset(subscriptions, request, view=self)

        serializer = self.serializer_class(
            result_page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data, "subscriptions")


class MySubscriptionDetailAPIView(APIView):
    serializer_class = GymSubscriptionReadSerializer

    def get(self, request, subscription_id):

        subscription = GymSubscription.objects.get_subscription(
            subscription_id=subscription_id,
            subscriber=request.user,
        )

        serializer = self.serializer_class(
            subscription,
            context={"request": request},
        )

        return Response({"subscription": serializer.data}, status=status.HTTP_200_OK)


class CancelSubscriptionAPIView(APIView):
    serializer_class = GymSubscriptionReadSerializer

    def post(self, request, subscription_id):

        subscription = GymSubscription.objects.get_subscription(
            subscription_id=subscription_id,
            subscriber=request.user,
        )

        GymSubscription.objects.cancel_subscription(subscription)

        return Response(status=status.HTTP_200_OK)
