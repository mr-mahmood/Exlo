# gym_subscriptions/views.py

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from core.pagination import CustomPagination
from .models import GymSubscription
from .serializers import GymSubscriptionReadSerializer
from core.cache import (
    USER_SUBSCRIPTIONS,
    USER_SUBSCRIPTION,
    cache_key,
    get_cache,
)


class MySubscriptionListAPIView(APIView):
    pagination_class = CustomPagination
    serializer_class = GymSubscriptionReadSerializer

    def get(self, request):
        key = cache_key(USER_SUBSCRIPTIONS, request.user.id, request=request)

        def build():
            subscriptions = GymSubscription.objects.select_related(
                "plan",
                "plan__gym",
            ).filter(subscriber=request.user)

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

            return paginator.get_paginated_data(serializer.data, "subscriptions")

        data = get_cache(key, build)
        return Response(data, status=status.HTTP_200_OK)


class MySubscriptionDetailAPIView(APIView):
    serializer_class = GymSubscriptionReadSerializer

    def get(self, request, subscription_id):
        key = cache_key(USER_SUBSCRIPTION, request.user.id, subscription_id)

        def build():
            subscription = GymSubscription.objects.get_subscription(
                subscription_id=subscription_id,
                subscriber=request.user,
            )
            serializer = self.serializer_class(
                subscription,
                context={"request": request},
            )
            return {"subscription": serializer.data}

        data = get_cache(key, build)
        return Response(data, status=status.HTTP_200_OK)


class CancelSubscriptionAPIView(APIView):
    def post(self, request, subscription_id):

        # this cancell a user subscription with there demand and remove it
        # its diffrent from refunding
        subscription = GymSubscription.objects.get_subscription(
            subscription_id=subscription_id,
            subscriber=request.user,
        )

        GymSubscription.objects.cancel_subscription(subscription)
        return Response(status=status.HTTP_200_OK)


class RefundSubscriptionAPIView(APIView):
    def post(self, request, subscription_id):
        # TODO: implement the avalability of canceling and refunding
        # with rule that all suncription from active and pendings
        # can be refund if they are within there first 48 hours and have not been used(no check in and visit consuming)
        # if the condition fullfill then we refund and cancel the sunsription if not we return error
        pass
