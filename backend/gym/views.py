# gym/views.py

from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from authentication.permissions import IsAdmin
from gym_auth.permissions import IsAdminOrGymOwner
from gym.models import Gym, GymPhotos
from core.pagination import CustomPagination
from core.errors import APIError, GymError
from typing import cast
from gym.serializers import GymSerializer, GymPhotoSerializer


class GymListAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GymSerializer
    pagination_class = CustomPagination

    def get(self, request):
        gyms = Gym.objects.filter(is_active=True).prefetch_related("photos")

        paginator = self.pagination_class()
        result_page = paginator.paginate_queryset(gyms, request, view=self)

        serializer = self.serializer_class(
            result_page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data, "gyms")


class GymDetailAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GymSerializer

    def get(self, request, gym_id):
        try:
            gym = Gym.objects.get(id=gym_id, is_active=True)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        serializer = self.serializer_class(
            gym,
            context={"request": request},
        )

        return Response({"gym": serializer.data}, status=status.HTTP_200_OK)


class GymCreateAPIView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = GymSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        gym = cast(Gym, serializer.save())

        return Response(
            {
                "gym": self.serializer_class(
                    gym,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class GymUpdateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymSerializer

    def put(self, request, gym_id):
        try:
            gym = Gym.objects.get(id=gym_id)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        serializer = self.serializer_class(
            gym,
            data=request.data,
            context={"request": request},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "gym": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class GymDeleteAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]

    def delete(self, request, gym_id):
        try:
            gym = Gym.objects.get(id=gym_id)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        # Check if gym has any active memberships
        if gym.has_active_memberships():
            raise APIError(GymError.GYM_HAS_ACTIVE_MEMBERSHIPS)

        gym.delete()

        return Response(status=status.HTTP_200_OK)


# ============================================================================
# PHOTO ENDPOINTS
# ============================================================================
class GymPhotosAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GymPhotoSerializer

    def get(self, request, gym_id):
        try:
            gym = Gym.objects.get(id=gym_id, is_active=True)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        photos = gym.photos.all()  # type: ignore

        serializer = self.serializer_class(
            photos,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "gym_photos": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class GymPhotoCreateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymPhotoSerializer

    def post(self, request, gym_id):
        try:
            gym = Gym.objects.get(id=gym_id, is_active=True)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        files = request.FILES.getlist("photos")

        if not files:
            raise APIError(GymError.PHOTO_FILE_REQUIRED)

        with transaction.atomic():
            for file in files:
                data = {"photo": file}
                serializer = self.serializer_class(
                    data=data,
                    context={
                        "request": request,
                        "gym": gym,
                    },
                )

                if not serializer.is_valid():
                    raise APIError(GymError.PHOTO_UPLOAD_FAILED)

                serializer.save()

        return Response(status=status.HTTP_201_CREATED)


class GymPhotoDeleteAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymPhotoSerializer

    def delete(self, request, gym_id, photo_id):
        try:
            gym = Gym.objects.get(id=gym_id, is_active=True)
        except Gym.DoesNotExist:
            raise APIError(GymError.GYM_NOT_FOUND)

        try:
            queryset = GymPhotos.objects.select_related("gym")
            if gym:
                queryset = queryset.filter(gym=gym)
            photo = queryset.get(id=photo_id)
        except GymPhotos.DoesNotExist:
            raise APIError(GymError.PHOTO_NOT_FOUND)

        if photo.photo:
            photo.photo.delete(save=False)

        photo.delete()

        return Response(status=status.HTTP_200_OK)
