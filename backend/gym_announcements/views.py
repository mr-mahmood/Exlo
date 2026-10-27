# gym_announcements/views.py

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from gym_auth.permissions import IsAdminOrGymOwner
from gym.models import Gym
from core.pagination import CustomPagination
from .models import GymAnnouncement
from .serializers import GymAnnouncementSerializer
from core.cache import GYM_ANNOUNCEMENTS, cache_key, get_cache, invalidate_cache


class GymAnnouncementAPIView(APIView):
    serializer_class = GymAnnouncementSerializer
    pagination_class = CustomPagination

    def get(self, request, gym_id):
        paginator = self.pagination_class()
        key = cache_key(GYM_ANNOUNCEMENTS, gym_id, request=request)

        def build():
            gym = Gym.objects.get_gym(gym_id=gym_id)
            announcements = GymAnnouncement.objects.filter(
                gym=gym,
                status=GymAnnouncement.Status.PUBLISHED,
            ).select_related("author")
            result_page = paginator.paginate_queryset(announcements, request, view=self)
            serializer = self.serializer_class(
                result_page,
                many=True,
                context={"request": request},
            )
            return paginator.get_paginated_data(serializer.data, "announcements")

        data = get_cache(key, build)
        return Response(data, status=status.HTTP_200_OK)


class GymAnnouncementCreateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymAnnouncementSerializer

    def post(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id=gym_id)

        serializer = self.serializer_class(
            data=request.data,
            context={"request": request, "gym": gym},
        )
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save(author=request.user)

        invalidate_cache(GYM_ANNOUNCEMENTS, gym.id)

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
        gym = Gym.objects.get_gym(gym_id)

        announcement = GymAnnouncement.objects.get_announcement(
            announcement_id=announcement_id,
            gym=gym,
        )

        serializer = self.serializer_class(
            announcement,
            data=request.data,
            context={"request": request, "gym": gym},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(author=request.user)

        invalidate_cache(GYM_ANNOUNCEMENTS, gym.id)

        return Response({"announcement": serializer.data}, status=status.HTTP_200_OK)


class GymAnnouncementDeleteAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]

    def delete(self, request, gym_id, announcement_id):
        gym = Gym.objects.get_gym(gym_id)

        announcement = GymAnnouncement.objects.get_announcement(
            announcement_id=announcement_id,
            gym=gym,
        )
        announcement.delete()

        invalidate_cache(GYM_ANNOUNCEMENTS, gym.id)

        return Response(status=status.HTTP_200_OK)
