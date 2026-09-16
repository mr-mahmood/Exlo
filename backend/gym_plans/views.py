# gym_plans/views.py

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from gym_auth.permissions import IsAdminOrGymOwner
from gym.models import Gym
from gym_plans.serializers import GymMembershipPlanSerializer
from gym_plans.models import GymMembershipPlan


class GymPlansAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GymMembershipPlanSerializer

    def get(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id=gym_id, active_only=True)

        plans = GymMembershipPlan.objects.get_gym_plans(gym=gym, active_only=True)

        serializer = self.serializer_class(
            plans,
            many=True,
            context={"request": request},
        )

        return Response({"plans": serializer.data}, status=status.HTTP_200_OK)


class GymPlansCreateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymMembershipPlanSerializer

    def post(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id=gym_id, active_only=True)

        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        plan = GymMembershipPlan.objects.create_plan(
            gym=gym,
            **serializer.validated_data,  # type: ignore
        )

        return Response(
            {
                "plan": self.serializer_class(
                    plan,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class GymPlansUpdateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymMembershipPlanSerializer

    def put(self, request, gym_id, plan_id):
        gym = Gym.objects.get_gym(gym_id=gym_id, active_only=True)

        plan = GymMembershipPlan.objects.get_plan(
            plan_id=plan_id,
            gym=gym,
            active_only=True,
        )

        serializer = self.serializer_class(
            plan,
            data=request.data,
            context={"request": request},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({"plan": serializer.data}, status=status.HTTP_200_OK)


class GymPlansDeleteAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]

    def delete(self, request, gym_id, plan_id):
        gym = Gym.objects.get_gym(gym_id=gym_id, active_only=True)

        plan = GymMembershipPlan.objects.get_plan(
            plan_id=plan_id,
            gym=gym,
            active_only=True,
        )

        plan.soft_delete()
        return Response(status=status.HTTP_200_OK)
