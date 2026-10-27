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
    invalidate_cache,
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
    serializer_class = GymSubscriptionReadSerializer

    def post(self, request, subscription_id):

        subscription = GymSubscription.objects.get_subscription(
            subscription_id=subscription_id,
            subscriber=request.user,
        )

        GymSubscription.objects.cancel_subscription(subscription)
        invalidate_cache(USER_SUBSCRIPTIONS, request.user.id)
        invalidate_cache(USER_SUBSCRIPTION, request.user.id, subscription.id)
        return Response(status=status.HTTP_200_OK)
