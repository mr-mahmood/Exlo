# gym_announcements/views.py

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from gym_auth.permissions import IsAdminOrGymOwner, IsGymMember
from gym.models import Gym
from core.pagination import CustomPagination
from core.errors import APIError, GymAnnouncementError, GymError
from .models import GymAnnouncement
from .serializers import GymAnnouncementSerializer


class GymAnnouncementAPIView(APIView):
    permission_classes = [IsGymMember]
    serializer_class = GymAnnouncementSerializer
    pagination_class = CustomPagination

    def get(self, request, gym_id):
        try:
            gym = Gym.objects.get(id=gym_id, is_active=True)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        announcements = GymAnnouncement.objects.filter(
            gym=gym,
            status=GymAnnouncement.Status.PUBLISHED,
        ).select_related("author")

        paginator = self.pagination_class()
        result_page = paginator.paginate_queryset(announcements, request, view=self)

        serializer = self.serializer_class(
            result_page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data, "announcements")


class GymAnnouncementCreateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymAnnouncementSerializer

    def post(self, request, gym_id):
        try:
            gym = Gym.objects.get(id=gym_id, is_active=True)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        serializer = self.serializer_class(
            data=request.data,
            context={"request": request, "gym": gym},
        )
        serializer.is_valid(raise_exception=True)

        announcement = serializer.save(author=request.user)

        return Response(
            {
                "announcement": self.serializer_class(
                    announcement,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class GymAnnouncementUpdateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymAnnouncementSerializer

    def put(self, request, gym_id, announcement_id):
        try:
            gym = Gym.objects.get(id=gym_id, is_active=True)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        try:
            announcement = GymAnnouncement.objects.get(
                id=announcement_id,
                gym=gym,
            )
        except GymAnnouncement.DoesNotExist:
            raise APIError(GymAnnouncementError.ANNOUNCEMENT_NOT_FOUND)

        serializer = self.serializer_class(
            announcement,
            data=request.data,
            context={"request": request, "gym": gym},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save(author=request.user)

        return Response(
            {
                "announcement": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class GymAnnouncementDeleteAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]

    def delete(self, request, gym_id, announcement_id):
        try:
            gym = Gym.objects.get(id=gym_id, is_active=True)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        try:
            announcement = GymAnnouncement.objects.get(
                id=announcement_id,
                gym=gym,
            )
        except GymAnnouncement.DoesNotExist:
            raise APIError(GymAnnouncementError.ANNOUNCEMENT_NOT_FOUND)

        announcement.delete()

        return Response(status=status.HTTP_200_OK)
